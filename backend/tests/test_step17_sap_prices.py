"""ราคาสินค้าจาก SAP (ZAIBAPI_MATERIAL_GET_ALL) — สูตรคิดราคาและด่านกันราคาเพี้ยน

เทสต์ตรงที่ "การแปลงข้อมูล" ล้วนๆ ไม่ยิง SAP จริง เพราะสิ่งที่พังได้คือการตีความ
บรรทัดเงื่อนไข ไม่ใช่การต่อเน็ต · ตัวเลขในนี้ลอกมาจากคำตอบจริงของ SAP
"""
from decimal import Decimal

import pytest

from app.integrations.sap.material_catalog import (
    ConditionLine,
    MaterialPriceRow,
    strip_matnr,
)


def _row(matnr: str, *conds: tuple[str, str, str]) -> MaterialPriceRow:
    return MaterialPriceRow(matnr=matnr, name="ทดสอบ",
                            conditions=[ConditionLine(k, Decimal(v), u) for k, v, u in conds])


def test_ตัดศูนย์นำหน้ารหัสสินค้า():
    """SAP คืน MATNR 18 หลักเติมศูนย์ ถ้าไม่ตัดจะจับคู่กับรหัสในฐานเราไม่ได้เลย"""
    assert strip_matnr("000000000019210764") == "19210764"
    assert strip_matnr("A534") == "A534"          # รหัสตัวอักษรไม่มีศูนย์นำ ต้องไม่โดนแตะ
    assert strip_matnr("") == ""


def test_สูตรราคาตรงกับของจริง():
    """เตียง FANTASY-B: 5,490 × (1 − 20%) − 2 = 4,390 ซึ่งเป็นราคาที่ขายอยู่จริง"""
    r = _row("19210764", ("PR01", "5490", "THB"), ("ZD01", "-20", "%"), ("ZD39", "-2", "THB"))
    assert r.list_price == Decimal(5490)
    assert r.net_price() == Decimal("4390.00")


def test_ลดเปอร์เซ็นต์ก่อนแล้วค่อยหักบาท():
    """ลำดับสำคัญ — สลับลำดับได้คนละราคา (โซฟา TRUMBLE ของจริง = 8,900)"""
    r = _row("19197054", ("PR01", "15200", "THB"), ("ZD01", "-15", "%"), ("ZD39", "-4020", "THB"))
    assert r.net_price() == Decimal("8900.00")
    # ถ้าหักบาทก่อนแล้วค่อยลด % จะได้ 9,503 ซึ่งผิด
    assert r.net_price() != Decimal("9503.00")


def test_ตัวโชว์ไม่มีส่วนลดขายราคาป้ายเต็ม():
    """SAP ส่งตัวโชว์ (20xxxxxxx) มาพร้อมแต่ PR01 อย่างเดียว ไม่มีบรรทัดส่วนลด"""
    r = _row("20210764", ("PR01", "5490", "THB"))
    assert r.net_price() == Decimal("5490.00")


def test_ส่วนลดสมาชิกต้องไม่ถูกนับรวมในราคาปกติ():
    """ZD52 เป็นราคาคนละชั้น ถ้าเผลอนับรวมลูกค้าทั่วไปจะได้ราคาสมาชิกไปด้วย"""
    r = _row("19999999", ("PR01", "1000", "THB"), ("ZD01", "-10", "%"), ("ZD52", "-5", "%"))
    assert r.net_price() == Decimal("900.00")
    # กันออกโดยปริยาย — ถ้าสั่งให้รวมถึงจะได้อีกราคา
    assert r.net_price(skip=()) == Decimal("850.00")


def test_ส่วนลดหลายบรรทัดรวมกันได้():
    """กลุ่ม 59 ใช้ ZD36 ไม่ใช่ ZD39 — สูตรต้องไม่ผูกกับชื่อเงื่อนไขตัวใดตัวหนึ่ง"""
    r = _row("59000716", ("PR01", "67100", "THB"), ("ZD36", "-27200", "THB"))
    assert r.net_price() == Decimal("39900.00")


def test_ไม่มีราคาป้ายก็ไม่มีราคาขาย():
    """มีแต่บรรทัดส่วนลดโดยไม่มี PR01 = ข้อมูลไม่ครบ ต้องคืน None ไม่ใช่ 0"""
    assert _row("19000001", ("ZD01", "-20", "%")).net_price() is None


# ---------- ด่านกันราคาเพี้ยน ----------
def test_ราคาถูกผิดปกติต้องไม่ถูกเขียนลงฐาน(monkeypatch):
    """ชิ้นส่วนโซฟาในชุด: ป้าย 47,100 แต่ net 2,045 (4%) — ปล่อยผ่านแปลว่าขายขาดทุนมหาศาล"""
    from app.etl import sync_sap_prices as m

    snap = {"display": {
        "20240895": {"name": "ชิ้นส่วนโซฟา", "list": "47100.00", "net": "2045.00", "discounts": []},
        "20210764": {"name": "เตียงปกติ", "list": "5490.00", "net": "5490.00", "discounts": []},
    }}
    res = m.apply_to_db(snap, dry_run=True)
    assert [x[0] for x in res["suspicious"]] == ["20240895"]

    # โปรลดราคาจริง 40-60% ต้องผ่านด่านนี้ไปได้ ไม่งั้นด่านนี้ขวางงานปกติ
    snap2 = {"display": {"20052168": {"name": "โซฟาเบดลดราคา", "list": "18800.00",
                                      "net": "7500.00", "discounts": []}}}
    assert m.apply_to_db(snap2, dry_run=True)["suspicious"] == []


def test_ราคาหลอกไม่ทับของเดิม():
    """SAP ตอบ 1 บาทสำหรับรหัสที่ยังไม่ตั้งราคา — ต้องข้าม ไม่ใช่เขียนทับ"""
    from app.etl import sync_sap_prices as m

    snap = {"display": {"20251932": {"name": "ยังไม่ตั้งราคา", "list": "1.00",
                                     "net": "1.00", "discounts": []}}}
    res = m.apply_to_db(snap, dry_run=True)
    assert res["skipped_no_price"] == 1 and res["added"] == 0 and res["changed"] == []


@pytest.fixture
def priced_pair():
    """วางราคาเดิมไว้ให้คู่ 19/20 แล้วเก็บกวาดหลังเทสต์ — ฐานทดสอบใช้ร่วมกันทั้ง session"""
    from sqlalchemy import delete
    from app.db.session import SessionLocal
    from app.models.catalog import Material, MaterialPrice

    codes = ("19777001", "20777001")

    def clean(db):
        db.execute(delete(MaterialPrice).where(MaterialPrice.matnr.in_(codes)))
        db.execute(delete(Material).where(Material.matnr.in_(codes)))

    with SessionLocal() as db:
        clean(db)
        for c in codes:
            # material_prices มี FK ไป materials ต้องมีตัวสินค้าก่อน
            db.add(Material(matnr=c, sku=c, name_th="สินค้าทดสอบราคา"))
        db.flush()
        for c in codes:
            db.add(MaterialPrice(matnr=c, tier="standard", price=Decimal("4390.00")))
        db.commit()
    yield codes
    with SessionLocal() as db:
        clean(db)
        db.commit()


def test_เขียนเฉพาะตัวโชว์ไม่แตะสินค้าปกติ(priced_pair):
    """ราคาขายของ 19xxx มาจาก sb_products ซึ่งคิดมาถูกแล้ว งานนี้ต้องไม่ไปทับ

    ถ้าเผลอเขียนทับ ราคาหน้าเว็บจะเปลี่ยนโดยไม่มีใครสั่ง และสองแหล่งจะเริ่มไม่ตรงกัน
    """
    from app.etl import sync_sap_prices as m
    from app.db.session import SessionLocal
    from app.models.catalog import MaterialPrice
    from sqlalchemy import select

    normal, display = priced_pair
    # snapshot แยกสองกอง — 19 อยู่ใน regular ซึ่ง apply_to_db ไม่อ่านเลย
    snap = {
        "regular": {normal: {"name": "x", "list": "5490.00", "net": "4390.00", "discounts": []}},
        "display": {display: {"name": "x", "list": "5490.00", "net": "5490.00",
                              "discounts": [], "pair": normal}},
    }
    res = m.apply_to_db(snap, dry_run=False)
    try:
        assert [c for c, *_ in res["changed"]] == [display]
        with SessionLocal() as db:
            got = {p.matnr: p.price for p in db.scalars(
                select(MaterialPrice).where(MaterialPrice.tier == "standard",
                                            MaterialPrice.matnr.in_((normal, display))))}
        assert got[normal] == Decimal("4390.00")      # ของเดิม ไม่ถูกแตะ
        assert got[display] == Decimal("5490.00")     # ตัวโชว์ถูกแก้เป็นราคาเต็ม
    finally:
        pass


def test_ตัวโชว์ที่มีส่วนลดต้องคิดให้ก่อนเก็บ():
    """หายากแต่มีจริง (เจอ 1 ตัวในทั้ง catalog) — ถ้าไม่คิดจะเก็บราคาป้ายไปแทน"""
    r = _row("20113890", ("PR01", "15200", "THB"), ("ZD01", "-10", "%"))
    assert r.net_price() == Decimal("13680.00")


def test_จับคู่รหัสตัวโชว์กับตัวหลัก():
    from app.etl.sync_sap_prices import display_of

    assert display_of("19210764") == "20210764"
