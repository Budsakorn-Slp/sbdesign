"""เอกสารใบเสนอราคา — สิ่งที่ลูกค้าถือกลับบ้าน

เอกสารนี้ไม่มีใครเห็นตอนรันเทสปกติ ผิดแล้วไปรู้เอาตอนลูกค้าถามว่าทำไมคิดค่าส่งสองรอบ
เทสจึงอ่าน HTML จริงที่ออกมา ไม่ใช่เช็คว่าฟังก์ชันถูกเรียก
"""
import re

import pytest

from app.db.session import SessionLocal
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


def _quotation(client, hs, note="วัดห้องแล้ว ส่งเช้าเท่านั้น"):
    from tests.test_step8_quotation import _ready_cart

    cart, _ = _ready_cart(client, hs)
    p = client.post("/presos", json={"cart_id": cart["id"], "note": note}, headers=hs).json()
    r = client.post(f"/presos/{p['preso_no']}/quotation", json={"force": True}, headers=hs)
    assert r.status_code == 201, r.text
    return r.json(), p


def _doc(client, hs, no, images=False):
    r = client.get(f"/quotations/{no}/document", params={"images": "1"} if images else None, headers=hs)
    assert r.status_code == 200, r.text
    return r.text


def test_ค่าขนส่งต้องไม่โผล่สองรอบ(client):
    """บรรทัดค่าบริการที่เปิด Mat (A534) เคยอยู่ในตารางสินค้าด้วย แล้วมีช่อง "ค่าขนส่ง"
    ข้างล่างอีก ลูกค้าอ่านแล้วเห็นเลขเดียวกันสองที่ทั้งที่ยอดรวมนับครั้งเดียว"""
    hs = auth_headers(client, "SA-104", "staff")
    q, _ = _quotation(client, hs)
    doc = _doc(client, hs, q["quotation_no"])
    body = doc[doc.index("<tbody>"):doc.index("</tbody>")]
    assert "A534" not in body.split("รวมสินค้า")[0], "บรรทัดค่าบริการต้องไม่อยู่ในตารางสินค้า"


def test_ส่วนลดยอดศูนย์ต้องไม่พิมพ์(client):
    """"ส่งฟรีในเขต กทม. 0.00" คู่กับ "ค่าขนส่ง 600" อ่านแล้วขัดกันเอง"""
    hs = auth_headers(client, "SA-104", "staff")
    q, _ = _quotation(client, hs)
    doc = _doc(client, hs, q["quotation_no"])
    assert not re.search(r">-0\.00<", doc), "มีแถวส่วนลด 0.00 หลุดออกมา"


def test_โชว์เบอร์พนักงานไม่ใช่คิวจัดส่ง(client):
    """คิวจัดส่งเปลี่ยนได้หลังออกใบ พิมพ์ค้างไว้จะเป็นข้อมูลผิดในมือลูกค้า"""
    from sqlalchemy import select

    from app.models.user import User

    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.staff_code == "SA-104"))
        u.phone = "0812345678"
        db.commit()
    hs = auth_headers(client, "SA-104", "staff")
    q, _ = _quotation(client, hs)
    doc = _doc(client, hs, q["quotation_no"])
    assert "คิวจัดส่ง" not in doc
    assert "โทร 0812345678" in doc


def test_พนักงานไม่มีเบอร์_ต้องไม่พิมพ์โทรขีด(client):
    """"โทร -" คือช่องว่างที่กินที่แล้วไม่ได้บอกอะไร — ไม่มีเบอร์ให้ใช้อีเมลแทน"""
    from sqlalchemy import select

    from app.models.user import User

    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.staff_code == "SA-104"))
        u.phone = None
        db.commit()
    hs = auth_headers(client, "SA-104", "staff")
    q, _ = _quotation(client, hs)
    doc = _doc(client, hs, q["quotation_no"])
    assert "โทร -" not in doc
    assert "somchai@sb.local" in doc


def test_ช่องหมายเหตุอยู่เหนือตารางสินค้า(client):
    """เซลล์ขอให้อยู่ข้างบน จะได้อ่านเงื่อนไขก่อนไล่ดูรายการ ไม่ใช่เจอทีหลังตอนอ่านจบแล้ว"""
    hs = auth_headers(client, "SA-104", "staff")
    q, _ = _quotation(client, hs, note="ลูกค้าขอส่งหลัง 15 น.")
    doc = _doc(client, hs, q["quotation_no"])
    assert doc.index("หมายเหตุ") < doc.index("<table>"), "ช่องหมายเหตุต้องมาก่อนตารางสินค้า"


def test_มีช่องหมายเหตุและแสดงที่เซลล์พิมพ์ไว้(client):
    hs = auth_headers(client, "SA-104", "staff")
    q, _ = _quotation(client, hs, note="ลูกค้าขอส่งหลัง 15 น.")
    doc = _doc(client, hs, q["quotation_no"])
    assert "หมายเหตุ" in doc and "ลูกค้าขอส่งหลัง 15 น." in doc


def test_มีช่องส่วนลดต่อบรรทัด(client):
    hs = auth_headers(client, "SA-104", "staff")
    q, _ = _quotation(client, hs)
    doc = _doc(client, hs, q["quotation_no"])
    head = doc[doc.index("<thead>"):doc.index("</thead>")]
    assert "ส่วนลด" in head and "ราคา/หน่วย" in head


def test_pdf_สองแบบ_มีรูปกับไม่มีรูป(client):
    from app.models.catalog import Material

    hs = auth_headers(client, "SA-104", "staff")
    q, _ = _quotation(client, hs)
    with SessionLocal() as db:  # ของ seed ไม่มีรูป — ใส่ให้ก่อนถึงจะวัดได้ว่ารูปขึ้นจริง
        for ln in q["lines"]:
            m = db.get(Material, ln["matnr"])
            if m:
                m.image_url = f"https://cdn.sb.com/{ln['matnr']}.jpg"
        db.commit()
    plain = _doc(client, hs, q["quotation_no"])
    withimg = _doc(client, hs, q["quotation_no"], images=True)
    assert "<img" not in plain
    assert "<img" in withimg, "แบบมีรูปต้องมีรูปสินค้าจริง"
    # เนื้อหาเหมือนกันทุกอย่างยกเว้นรูป — ยอดต้องไม่เพี้ยนตามแบบเอกสาร
    assert f"{float(q['grand_total']):,.2f}" in plain
    assert f"{float(q['grand_total']):,.2f}" in withimg


def test_หน้าเพรโซ่ส่ง_token_ให้เปิดเอกสารแท็บใหม่ได้(client):
    """ปุ่ม PDF เปิดแท็บใหม่ ซึ่งไม่มี Authorization header ติดไปด้วย"""
    hs = auth_headers(client, "SA-104", "staff")
    q, p = _quotation(client, hs)
    row = next(x for x in client.get("/presos", params={"status": "quoted"}, headers=hs).json() if x["preso_no"] == p["preso_no"])
    assert row["quotation_token"], "ต้องมี token ให้พนักงาน"
    # เปิดได้จริงโดยไม่ต้องล็อกอิน
    r = client.get(f"/quotations/{q['quotation_no']}/document", params={"t": row["quotation_token"], "images": "1"})
    assert r.status_code == 200 and "ใบเสนอราคา" in r.text


def test_ลูกค้าไม่ได้_token_ติดมาด้วย(client):
    hs = auth_headers(client, "SA-104", "staff")
    _quotation(client, hs)
    ch = auth_headers(client, "0949164600")
    for row in client.get("/presos", headers=ch).json():
        assert row["quotation_token"] is None


def test_เงื่อนไขชำระเงินกับบัญชีบริษัทขึ้นเมื่อตั้งค่าแล้ว(client, monkeypatch):
    """ไม่ตั้งค่า = ไม่พิมพ์ · ดีกว่าพิมพ์เลขบัญชีตัวอย่างค้างไว้แล้วมีคนโอนผิดที่"""
    from app.core.config import get_settings

    hs = auth_headers(client, "SA-104", "staff")
    q, _ = _quotation(client, hs)
    assert "โอนเข้าบัญชี" not in _doc(client, hs, q["quotation_no"])

    s = get_settings()
    monkeypatch.setattr(s, "quotation_payment_terms", "ชำระเต็มจำนวนก่อนจัดส่ง")
    monkeypatch.setattr(s, "company_bank_name", "ธนาคารกสิกรไทย")
    monkeypatch.setattr(s, "company_bank_account_name", "บริษัท เอส.บี.อุตสาหกรรมเครื่องเรือน จำกัด")
    monkeypatch.setattr(s, "company_bank_account_no", "123-4-56789-0")
    doc = _doc(client, hs, q["quotation_no"])
    assert "ชำระเต็มจำนวนก่อนจัดส่ง" in doc and "123-4-56789-0" in doc and "ธนาคารกสิกรไทย" in doc
