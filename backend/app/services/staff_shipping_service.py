"""ค่าขนส่งฝั่งพนักงาน — หน้า /sales เท่านั้น

ทำไมต้องมีชุดแยกจากค่าส่งหน้าเว็บ:
  หน้าเว็บลูกค้าคิดค่าส่งจากกฎ Amasty ที่ยกมาจาก Magento (ship_rules/ship_rates) ซึ่งผูกกับ
  รหัสไปรษณีย์ น้ำหนัก และธงรายสินค้า · แต่งานขายหน้าสาขาคิดคนละแบบ: ดูยอดบิลอย่างเดียว
  แล้ว "เปิด Mat" ค่าขนส่งเป็นบรรทัดสินค้าจริงในใบเสนอราคา (A534 / A761) แบบที่ SAP ต้องการ

  สองชุดนี้จึงอยู่คนละที่โดยตั้งใจ ห้ามเอามารวมกัน — แก้ชุดหนึ่งต้องไม่กระทบอีกชุด

กฎเก็บเป็น JSON (seed/shipping/staff_shipping.json) ไม่ได้ฝังในโค้ด เพราะทีมขายแก้ตัวเลข
เองได้โดยไม่ต้อง deploy · อ่านใหม่อัตโนมัติเมื่อไฟล์ถูกแก้ (เช็ค mtime ทุก 60 วินาที)
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.cart import Cart, CartItem
from app.models.common import utcnow
from app.services import audit_service, cart_service

RULES_PATH = Path(__file__).resolve().parents[2] / "seed" / "shipping" / "staff_shipping.json"
_RELOAD_AFTER_SEC = 60

_cache: dict[str, Any] = {"data": None, "mtime": 0.0, "checked": 0.0}


def _load() -> dict:
    import time

    now = time.time()
    if _cache["data"] is not None and now - _cache["checked"] < _RELOAD_AFTER_SEC:
        return _cache["data"]
    _cache["checked"] = now
    try:
        mtime = RULES_PATH.stat().st_mtime
    except OSError:
        raise HTTPException(status_code=500, detail="ไม่พบไฟล์กฎค่าขนส่งของพนักงาน")
    if _cache["data"] is None or mtime != _cache["mtime"]:
        _cache["data"] = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        _cache["mtime"] = mtime
    return _cache["data"]


REMOTE_PATH = Path(__file__).resolve().parents[2] / "seed" / "shipping" / "remote_areas.json"
_remote: dict[str, Any] = {"data": None, "mtime": 0.0, "checked": 0.0}


def _load_remote() -> dict:
    """พื้นที่ห่างไกล — แยกไฟล์จากเทียร์ค่าขนส่ง เพราะคนละทีมเป็นเจ้าของข้อมูล
    (เทียร์มาจากทีมขาย · พื้นที่ห่างไกลมาจากทีมขนส่ง) แก้คนละรอบกัน
    """
    import time

    now = time.time()
    if _remote["data"] is not None and now - _remote["checked"] < _RELOAD_AFTER_SEC:
        return _remote["data"]
    _remote["checked"] = now
    try:
        mtime = REMOTE_PATH.stat().st_mtime
    except OSError:
        return {"areas": []}
    if _remote["data"] is None or mtime != _remote["mtime"]:
        _remote["data"] = json.loads(REMOTE_PATH.read_text(encoding="utf-8"))
        _remote["mtime"] = mtime
    return _remote["data"]


def remote_area(province: str, district: str | None = None) -> dict | None:
    """จังหวัด/อำเภอนี้เป็นพื้นที่ห่างไกลไหม — คืนค่าส่งเพิ่มถ้าใช่

    เทียบชื่อแบบตัดคำนำหน้าออก เพราะข้อมูลที่อยู่ไทยเขียนได้หลายแบบ
    ("เกาะสมุย" / "อ.เกาะสมุย" / "อำเภอเกาะสมุย")
    """
    norm = _norm_place
    pv, dt = norm(province), norm(district)
    hit = None
    for a in _load_remote().get("areas", []):
        if norm(a.get("province")) != pv:
            continue
        ad = norm(a.get("district")) if a.get("district") else None
        if ad is None:
            hit = hit or a          # ทั้งจังหวัด — เก็บไว้เป็นตัวสำรอง
        elif dt and ad == dt:
            return a                # ตรงอำเภอเป๊ะ ชนะเสมอ
    return hit


def fleets() -> list[dict]:
    """รายการ fleet ให้พนักงานเลือก — ชุดรถ/ทีมส่งคนละแบบ คิดค่าเดินทางคนละเรตได้"""
    return _load_remote().get("fleets", [])


def _norm_place(v: str | None) -> str:
    """ตัดคำนำหน้าออกก่อนเทียบชื่อ — ข้อมูลที่อยู่ไทยเขียนได้หลายแบบ
    ("เกาะสมุย" / "อ.เกาะสมุย" / "อำเภอเกาะสมุย" · "ภูเก็ต" / "จ.ภูเก็ต")
    """
    v = (v or "").strip()
    for p in ("จังหวัด", "จ.", "อำเภอ", "เขต", "อ."):
        if v.startswith(p):
            v = v[len(p):]
    return v.strip()


DISTRICT_PATH = Path(__file__).resolve().parents[2] / "seed" / "shipping" / "district_fees.json"
_districts: dict[str, Any] = {"data": None, "mtime": 0.0, "checked": 0.0, "index": {}}


def _load_districts() -> dict:
    """ตารางค่าจัดส่งรายอำเภอจากทีมขนส่ง — 863 อำเภอ ทำ index ไว้ในหน่วยความจำรอบเดียว

    ไฟล์นี้เปลี่ยนไม่บ่อย (ปีละไม่กี่ครั้ง) แต่ถูกอ่านทุกครั้งที่พนักงานกดเช็ค
    ไล่ลิสต์ 863 แถวทุกครั้งเปล่าประโยชน์ เลยทำ dict ไว้ตอนโหลด
    """
    import time

    now = time.time()
    if _districts["data"] is not None and now - _districts["checked"] < _RELOAD_AFTER_SEC:
        return _districts
    _districts["checked"] = now
    try:
        mtime = DISTRICT_PATH.stat().st_mtime
    except OSError:
        _districts["data"] = {"rows": [], "special_fee": 10000}
        _districts["index"] = {}
        return _districts
    if _districts["data"] is None or mtime != _districts["mtime"]:
        data = json.loads(DISTRICT_PATH.read_text(encoding="utf-8"))
        _districts["data"] = data
        _districts["mtime"] = mtime
        _districts["index"] = {(_norm_place(r["province"]), _norm_place(r["district"])): r for r in data.get("rows", [])}
    return _districts


def district_fee(province: str, district: str | None) -> dict:
    """ค่าจัดส่งของอำเภอนี้ — ใช้ตัวเลขในตารางตรงๆ ทุกกรณี

      in_table=False   จังหวัดไม่อยู่ในตาราง = เขตส่งฟรี (กทม. นนทบุรี ปทุมธานี สมุทรปราการ)
      found=False      จังหวัดอยู่ในตารางแต่ไม่เจออำเภอ (ชื่อสะกดไม่ตรง) — ไม่เดาว่าฟรี
      นอกนั้น          บวกตามตัวเลขในตาราง รวมถึงค่าสูงอย่าง 10,000 ของเกาะ/ชายแดนใต้
                       (ทีมขายยืนยันว่าเป็นค่าส่งจริง ถ้าส่งไม่ได้จริงก็ยกเลิกบิลเอง)
    """
    d = _load_districts()
    provinces = {p for p, _ in d["index"]}
    pv, dt = _norm_place(province), _norm_place(district)
    if pv not in provinces:
        return {"fee": Decimal(0), "found": False, "in_table": False}
    row = d["index"].get((pv, dt))
    if not row:
        return {"fee": Decimal(0), "found": False, "in_table": True}
    return {"fee": Decimal(str(row["fee"])), "found": True, "in_table": True}


def delivery_extra(province: str, district: str | None, fleet_code: str | None) -> dict:
    """ค่าจัดส่งเพิ่มเติมของปลายทางนี้ — คิดจากตารางรายอำเภอของทีมขนส่ง

    ชุดรถ (fleet) เก็บไว้เป็นข้อมูลประกอบว่าจะใช้รถชุดไหน ไม่ได้คิดเงินเพิ่มจากตรงนี้
    ค่าที่คิดจริงมาจากอำเภอปลายทางล้วนๆ
    """
    fleet = next((f for f in fleets() if f["code"] == fleet_code), None)
    hit = district_fee(province, district)
    return {
        "area": "free" if not hit["in_table"] else "upcountry",
        "area_label": "เขตส่งฟรี" if not hit["in_table"] else "ต่างจังหวัด",
        "fleet": fleet["name"] if fleet else None,
        "fleet_fee": "0",
        "remote": False,
        "remote_scope": district,
        "remote_note": "ไม่พบอัตราของอำเภอนี้ในตาราง — ตรวจกับทีมขนส่งก่อน" if hit["in_table"] and not hit["found"] else None,
        "remote_fee": str(hit["fee"]),
        "extra_total": str(hit["fee"]),
        # ต้องให้คนตรวจเฉพาะตอนหาอัตราไม่เจอเท่านั้น · ค่าสูงๆ ในตารางถือว่าเป็นค่าจริง
        "needs_review": hit["in_table"] and not hit["found"],
    }


def charge_matnrs() -> set[str]:
    """รหัสที่เป็น "ค่าบริการ" ไม่ใช่สินค้า — ต้องไม่ถูกนับเป็นยอดสินค้าตอนตัดสินเทียร์"""
    return set(_load().get("charges", {}))


def is_charge_line(item: CartItem) -> bool:
    return item.matnr in charge_matnrs()


def goods_subtotal(cart: Cart) -> Decimal:
    """ยอดสินค้าที่ติ๊กไว้ ไม่รวมบรรทัดค่าขนส่ง

    ถ้านับบรรทัดค่าขนส่งเข้าไปด้วย พอเพิ่มค่าขนส่ง 600 ยอดจะขยับ แล้วอาจข้ามไปเทียร์ถัดไป
    กลายเป็นค่าขนส่งเปลี่ยนตัวเอง วนไม่จบ
    """
    return sum((it.line_total for it in cart.selected_items if not is_charge_line(it)), Decimal("0"))


def _tier_for(subtotal: Decimal) -> dict:
    for t in _load()["tiers"]:
        lo = Decimal(str(t["min"]))
        hi = t.get("max")
        if subtotal >= lo and (hi is None or subtotal <= Decimal(str(hi))):
            return t
    # เทียร์สุดท้ายเปิดปลายไว้อยู่แล้ว ปกติมาไม่ถึงบรรทัดนี้ — กันไว้เผื่อมีคนแก้ JSON จนมีช่องโหว่
    raise HTTPException(status_code=500, detail=f"ยอด {subtotal} ไม่ตรงเทียร์ค่าขนส่งข้อไหนเลย — ตรวจไฟล์กฎ")


def role_of(matnr: str) -> str:
    return _load().get("charges", {}).get(matnr, {}).get("role", "tier")


def charge_lines(cart: Cart) -> list[CartItem]:
    """บรรทัดค่าขนส่งทั้งหมดในบิล — tier ก่อน extra ทีหลัง ตามลำดับที่ลูกค้าควรอ่าน"""
    lines = [it for it in cart.items if is_charge_line(it)]
    return sorted(lines, key=lambda it: 0 if role_of(it.matnr) == "tier" else 1)


def current_line(cart: Cart, role: str = "tier") -> CartItem | None:
    """บรรทัดค่าขนส่งของบทบาทนั้น — มีได้บทบาทละบรรทัดเดียว"""
    return next((it for it in cart.items if is_charge_line(it) and role_of(it.matnr) == role), None)


def options(role: str = "tier") -> list[dict]:
    """รหัสค่าบริการที่ให้พนักงานเลือกได้ในบทบาทนั้น — มาจากไฟล์กฎ ไม่ได้ฮาร์ดโค้ดในหน้าเว็บ

    เพิ่มรหัสใหม่ในไฟล์กฎแล้วช่องเลือกขึ้นเอง · ถ้าให้หน้าเว็บถือลิสต์ไว้เอง เติมรหัสทีต้องแก้
    สองที่แล้วลืมที่ใดที่หนึ่งทุกครั้ง
    """
    return [{"matnr": m, "name": c.get("name", m), "default_fee": None if c.get("default_fee") is None else str(Decimal(str(c["default_fee"])))}
            for m, c in _load().get("charges", {}).items() if c.get("role", "tier") == role]


def known_roles() -> list[str]:
    """บทบาททั้งหมดที่ไฟล์กฎประกาศไว้ — ใช้ตรวจ input แทนการเขียนรายชื่อตายไว้ใน API"""
    d = _load()
    declared = list(d.get("roles", {}))
    used = [c.get("role", "tier") for c in d.get("charges", {}).values()]
    return declared or sorted(set(used))


def picker_roles(cart: Cart) -> list[dict]:
    """บล็อกค่าบริการที่พนักงานเปิดเองได้ เรียงตามไฟล์กฎ

    หนึ่ง role = หนึ่งบรรทัดในบิล แต่ต่าง role บวกกันได้ เช่น ตัวโชว์ส่งต่างจังหวัด
    จะมี A052 (เหมา) + A761 (ตามยอด) + A533 (พื้นที่ห่างไกล) พร้อมกันสามบรรทัด
    """
    d = _load()
    out = []
    for role, meta in d.get("roles", {}).items():
        if not meta.get("picker"):
            continue          # extra เปิดจากเมนูจัดคิวส่ง ไม่ใช่กล่องนี้
        if not meta.get("enabled", True):
            continue          # ทำโครงไว้แล้วแต่ยังไม่เปิดใช้ — แก้ enabled ในไฟล์กฎเป็น true ก็ขึ้นเลย
        line = current_line(cart, role)
        opts = options(role)
        out.append({
            "role": role,
            "label": meta.get("label", role),
            "hint": meta.get("hint"),
            "options": opts,
            "default_matnr": (opts[0]["matnr"] if opts else None),
            "default_fee": (opts[0]["default_fee"] if opts else None),
            "current": None if not line else {
                "item_id": line.id, "matnr": line.matnr, "name": line.name_snapshot,
                "fee": str(line.unit_price_snapshot), "remark": line.note,
            },
        })
    return out


def suggest(cart: Cart) -> dict:
    """เสนอว่าบิลนี้ควรเปิด Mat ตัวไหน ราคาเท่าไร — ยังไม่เขียนอะไรลงตะกร้า"""
    data = _load()
    subtotal = goods_subtotal(cart)
    tier = _tier_for(subtotal)
    matnr = tier["matnr"]
    line = current_line(cart)
    return {
        "goods_subtotal": str(subtotal),
        "matnr": matnr,
        "name": data["charges"].get(matnr, {}).get("name", matnr),
        "fee": str(Decimal(str(tier["fee"]))),
        "tier_label": tier["label"],
        "editable": True,
        "options": options("tier"),
        # หนึ่งบล็อกต่อหนึ่งบทบาท — หน้าเว็บวาดตามนี้ ไม่ต้องรู้จักรหัสไหนเลย
        "roles": picker_roles(cart),
        "extra": None if not (ex := current_line(cart, "extra")) else {
            "item_id": ex.id, "matnr": ex.matnr, "name": ex.name_snapshot,
            "fee": str(ex.unit_price_snapshot), "remark": ex.note,
        },
        "current": None
        if not line
        else {
            "item_id": line.id,
            "matnr": line.matnr,
            "name": line.name_snapshot,
            "fee": str(line.unit_price_snapshot),
            "remark": line.note,
            "matches_rule": line.matnr == matnr and line.unit_price_snapshot == Decimal(str(tier["fee"])),
        },
    }


def apply(db: Session, cart: Cart, actor, matnr: str, fee: Decimal, remark: str | None) -> CartItem:
    """ใส่/แก้บรรทัดค่าขนส่งในตะกร้า — มีได้บรรทัดเดียวเสมอ

    เปลี่ยนรหัส (A534 <-> A761) ก็แก้บรรทัดเดิม ไม่สร้างใบใหม่ ไม่งั้นบิลจะมีค่าขนส่งสองบรรทัด
    """
    data = _load()
    if matnr not in data["charges"]:
        raise HTTPException(status_code=422, detail=f"รหัส {matnr} ไม่ใช่รหัสค่าขนส่งที่กำหนดไว้")
    if fee < 0:
        raise HTTPException(status_code=422, detail="ค่าขนส่งติดลบไม่ได้")
    name = data["charges"][matnr]["name"]
    line = current_line(cart, role_of(matnr))
    before = None if not line else f"{line.matnr} {line.unit_price_snapshot}"
    if line:
        line.matnr = matnr
        line.sku = matnr
        line.name_snapshot = name
        line.unit_price_snapshot = fee
        line.note = remark or None
    else:
        line = CartItem(
            cart_id=cart.id, matnr=matnr, sku=matnr, name_snapshot=name, qty=1,
            unit_price_snapshot=fee, price_tier="standard", added_by="sales",
            added_by_user_id=actor.id if actor else None, pending_ack=False,
            supply_mode="ship", note=remark or None,
        )
        db.add(line)
        cart.items.append(line)
    cart.updated_at = utcnow()
    # ค่าขนส่งไม่ใช่ของที่ต้องเช็คสต็อก/โปรฯ ใหม่ จึงไม่ bump rev — ไม่งั้นพนักงานแก้ค่าขนส่ง
    # ทีไร ด่านเช็คสต็อกกับโปรโมชั่นที่ผ่านไปแล้วจะถูกล้างทิ้ง ต้องกดใหม่ทุกครั้ง
    audit_service.log(db, actor, "cart.shipping_charge", "cart", cart.id,
                      {"matnr": matnr, "fee": str(fee), "remark": remark, "before": before})
    db.commit()
    db.refresh(line)
    cart_service.emit(cart, "shipping_charge", {"matnr": matnr, "fee": str(fee)})
    return line


def remove(db: Session, cart: Cart, actor, role: str = "tier") -> None:
    line = current_line(cart, role)
    if not line:
        raise HTTPException(status_code=404, detail="ตะกร้านี้ยังไม่มีบรรทัดค่าขนส่ง")
    audit_service.log(db, actor, "cart.shipping_charge_remove", "cart", cart.id,
                      {"matnr": line.matnr, "fee": str(line.unit_price_snapshot)})
    cart.items.remove(line)
    db.delete(line)
    cart.updated_at = utcnow()
    db.commit()
    cart_service.emit(cart, "shipping_charge", {"matnr": None, "fee": None})
