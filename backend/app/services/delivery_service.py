"""ค่าขนส่ง + คิวจัดส่ง: quote ผ่าน SapClient (โซน/ค่าส่ง/slot) → mirror ลง delivery_zones/delivery_slots → จอง slot ชั่วคราว 15 นาที"""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.sap import get_sap_client
from app.integrations.sap.base import DeliveryQuote, SapError
from app.models.cart import Cart
from app.models.common import utcnow
from app.models.delivery import DeliverySlot, DeliveryZone, SlotHold
from app.models.user import User
from app.services import audit_service, cart_service, promo_service, shipping_engine

HOLD_MINUTES = 15


@dataclass
class SlotView:
    id: str
    date: str
    period: str
    zone: str
    quota: int
    booked: int
    remaining: int
    held_by_this_cart: bool


def release_expired_holds(db: Session) -> int:
    now = utcnow()
    n = 0
    for h in db.scalars(select(SlotHold).where(SlotHold.released.is_(False), SlotHold.confirmed.is_(False), SlotHold.expires_at < now)).all():
        slot = db.get(DeliverySlot, h.slot_id)
        if slot and slot.booked > 0:
            slot.booked -= 1
        h.released = True
        cart = db.get(Cart, h.cart_id)
        if cart and cart.slot_id == h.slot_id:
            cart.slot_id = None
        n += 1
    if n:
        db.commit()
    return n


def active_hold(db: Session, cart: Cart) -> SlotHold | None:
    return db.scalar(select(SlotHold).where(SlotHold.cart_id == cart.id, SlotHold.released.is_(False)).order_by(SlotHold.created_at.desc()))


def _mirror_quote(db: Session, q: DeliveryQuote) -> None:
    z = db.get(DeliveryZone, q.postcode)
    if not z:
        z = DeliveryZone(postcode=q.postcode, zone=q.zone, base_fee=q.base_fee, install_fee=q.install_fee)
        db.add(z)
    z.zone = q.zone
    z.zone_name = q.zone_name
    z.base_fee = q.base_fee if q.base_fee else z.base_fee
    z.install_fee = q.install_fee if q.install_fee else z.install_fee
    z.synced_at = utcnow()
    for s in q.slots:
        row = db.get(DeliverySlot, s.id)
        if not row:
            db.add(DeliverySlot(id=s.id, date=s.date, period=s.period, zone=s.zone, quota=s.quota, booked=s.booked))
        else:
            row.quota = s.quota
            # booked ฝั่งเราอาจสูงกว่า SAP เพราะมี hold ที่ยังไม่ sync → เอาค่ามากกว่า
            row.booked = max(row.booked, s.booked)
    db.commit()


def quote(db: Session, cart: Cart, actor: User | None, postcode: str, address: str | None = None) -> dict:
    release_expired_holds(db)
    pc = (postcode or "").strip()
    if len(pc) != 5 or not pc.isdigit():
        raise HTTPException(status_code=422, detail="รหัสไปรษณีย์ต้องเป็นตัวเลข 5 หลัก")
    try:
        q = get_sap_client().quote_delivery(promo_service.cart_dto(db, cart), pc)
    except SapError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"คำนวณค่าขนส่งไม่ได้: {e}")
    _mirror_quote(db, q)
    changed_zone = cart.ship_zone != q.zone
    cart.ship_postcode = pc
    cart.ship_zone = q.zone
    if address is not None:
        cart.ship_address = address
    cart.install_fee = q.install_fee
    cart.delivery_quoted_at = utcnow()
    # ค่าส่งมาจากตารางของเราถ้ามี — SAP ยังเป็นเจ้าของเขต/คิวจัดส่งเหมือนเดิม
    ship = shipping_engine.quote(db, cart, pc, promo_service.compute_totals(db, cart).net_total) if shipping_engine.has_rules(db) else None
    base_fee = ship.fee if ship else q.base_fee
    cart.shipping_fee = base_fee
    if changed_zone and cart.slot_id:
        release_hold(db, cart, actor)  # โซนเปลี่ยน คิวเดิมใช้ไม่ได้
    audit_service.log(db, actor, "delivery.quote", "cart", cart.id, {"postcode": pc, "zone": q.zone, "base_fee": str(base_fee), "install_fee": str(q.install_fee), "ship_source": ship.source if ship else "sap_zone"})
    db.commit()
    return {
        "cart_id": cart.id, "postcode": pc, "zone": q.zone, "zone_name": q.zone_name, "base_fee": base_fee, "install_fee": q.install_fee, "total_fee": base_fee + q.install_fee,
        "groups": groups_of(db, cart, q.groups), "slots": slots_for_zone(db, cart, q.zone), "held_slot_id": cart.slot_id,
        "ship_area": ship.area_name if ship else None, "ship_source": ship.source if ship else "sap_zone",
        "ship_weight_kg": ship.weight_kg if ship else None, "ship_needs_review": bool(ship and ship.needs_review),
        "ship_warnings": ship.warnings if ship else [], "ship_trace": ship.trace if ship else [],
    }


def groups_of(db: Session, cart: Cart, groups: dict[str, list[str]]) -> list[dict]:
    names = {it.matnr: it for it in cart.selected_items}
    out = []
    labels = {"takeaway": "ยกกลับวันนี้", "ship": "จัดส่งจากคลัง", "install": "จัดส่ง + ติดตั้ง"}
    for key in ("takeaway", "ship", "install"):
        mats = groups.get(key, [])
        if not mats:
            continue
        items = [{"matnr": m, "name": names[m].name_snapshot, "qty": names[m].qty, "plant_code": names[m].plant_code} for m in mats if m in names]
        out.append({"mode": key, "label": labels[key], "items": items, "fee_note": "ฟรี" if key == "takeaway" else None})
    return out


def slots_for_zone(db: Session, cart: Cart, zone: str) -> list[SlotView]:
    today = utcnow().date()
    rows = db.scalars(select(DeliverySlot).where(DeliverySlot.zone == zone, DeliverySlot.date >= today).order_by(DeliverySlot.date, DeliverySlot.period)).all()
    return [SlotView(id=s.id, date=s.date.isoformat(), period=s.period, zone=s.zone, quota=s.quota, booked=s.booked, remaining=s.remaining, held_by_this_cart=cart.slot_id == s.id) for s in rows]


def hold_slot(db: Session, cart: Cart, actor: User | None, slot_id: str) -> dict:
    release_expired_holds(db)
    slot = db.get(DeliverySlot, slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="ไม่พบคิวจัดส่ง")
    if cart.ship_zone and slot.zone != cart.ship_zone:
        raise HTTPException(status_code=400, detail="คิวนี้อยู่คนละเขตกับที่อยู่จัดส่ง — คำนวณค่าส่งใหม่ก่อน")
    cur = active_hold(db, cart)
    if cur and cur.slot_id == slot_id:
        cur.expires_at = utcnow() + timedelta(minutes=HOLD_MINUTES)
        db.commit()
        return {"slot_id": slot_id, "expires_at": cur.expires_at, "remaining": slot.remaining}
    if slot.remaining <= 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="คิวเต็ม เลือกรอบอื่น")
    if cur:
        release_hold(db, cart, actor)
    slot.booked += 1
    hold = SlotHold(slot_id=slot.id, cart_id=cart.id, user_id=actor.id if actor else None, expires_at=utcnow() + timedelta(minutes=HOLD_MINUTES))
    db.add(hold)
    cart.slot_id = slot.id
    audit_service.log(db, actor, "delivery.slot_hold", "cart", cart.id, {"slot_id": slot.id})
    db.commit()
    cart_service.emit(cart, "delivery_changed", {"slot_id": slot.id})
    return {"slot_id": slot.id, "expires_at": hold.expires_at, "remaining": slot.remaining}


def release_hold(db: Session, cart: Cart, actor: User | None) -> None:
    cur = active_hold(db, cart)
    if cur and not cur.confirmed:
        slot = db.get(DeliverySlot, cur.slot_id)
        if slot and slot.booked > 0:
            slot.booked -= 1
        cur.released = True
    cart.slot_id = None
    db.commit()


def confirm_hold(db: Session, cart: Cart) -> SlotHold | None:
    """ตอนออกใบเสนอราคา: จองคิวถาวร (ไม่หมดอายุ)"""
    cur = active_hold(db, cart)
    if cur:
        cur.confirmed = True
        db.commit()
    return cur


def slot_of_cart(db: Session, cart: Cart) -> DeliverySlot | None:
    return db.get(DeliverySlot, cart.slot_id) if cart.slot_id else None


def shipping_summary(db: Session, cart: Cart, net_total: Decimal | None = None) -> dict:
    """ใช้ใน compute_totals: ค่าส่งของตะกร้านี้ ณ ตอนนี้

    ถ้ามีตารางค่าส่งของเรา (ETL จาก Magento แล้ว) ให้คิดสดทุกครั้ง เพราะกฎขึ้นกับยอดสุทธิ
    หลังหักส่วนลด — เก็บค่าที่ quote ไว้แล้วใช้ซ้ำจะเพี้ยนทันทีที่ลูกค้าเพิ่ม/ลดของหรือใส่โค้ด
    ยังไม่มีตาราง (dev/mock) ค่อยถอยไปใช้ค่าที่ SAP quote ไว้บนตะกร้าตามเดิม
    """
    from app.services import staff_shipping_service  # ตรงนี้กัน circular import

    # ตะกร้าที่พนักงานถือ คิดค่าขนส่งจาก "ยอดบิล" อย่างเดียว ไม่ถามปลายทาง
    # (กฎที่ทีมขายตกลงกัน: ต่ำกว่า 15,000 = 600 · 15,000 ขึ้นไป = 100-500 ตามเทียร์)
    #
    # ห้ามปล่อยให้กฎ Amasty ของหน้าเว็บลูกค้ามาคิดด้วย เพราะจะได้ค่าส่งสองต่อ
    # ที่อยู่ยังต้องกรอกอยู่ แต่เอาไว้จองคิวรถ/รู้ว่าส่งไปไหน ไม่ได้เอาไปคิดเงิน
    # เกณฑ์คือ "เปิด Mat แล้วหรือยัง" ไม่ใช่ "ใครถือตะกร้า" — ตะกร้าที่พนักงานเปิดให้ลูกค้า
    # แล้วลูกค้าไปจ่ายเองบนเว็บ ต้องคิดค่าส่งด้วยกฎของหน้าเว็บตามเดิม
    charges = [it for it in staff_shipping_service.charge_lines(cart) if it.selected]
    if charges:
        return {"install_fee": Decimal(0), "quoted": True, "zone": cart.ship_zone, "postcode": cart.ship_postcode,
                "shipping_fee": sum((c.line_total for c in charges), Decimal(0)),
                "ship_source": "staff_tier", "ship_needs_review": False, "ship_warnings": [],
                "ship_trace": [{"rule": c.matnr, "matched": True, "why": c.name_snapshot} for c in charges]}

    # ตะกร้าที่พนักงานถืออยู่ยังไม่ได้เปิด Mat = ยังไม่มีค่าส่ง ไม่ใช่ให้กฎออนไลน์คิดแทน
    # ค่าส่งหน้าร้านคิดคนละเกณฑ์ (ตามยอดบิล) ถ้าปล่อยกฎ Amasty ทำงาน บิลจะโชว์ 399
    # ซึ่งเป็นตัวเลขของช่องทางออนไลน์ แล้วพอพนักงานเปิด Mat จริงตัวเลขก็กระโดดอีกรอบ
    if cart.owner_sales_id:
        return {"install_fee": Decimal(0), "quoted": False, "zone": cart.ship_zone, "postcode": cart.ship_postcode,
                "shipping_fee": Decimal(0), "ship_source": "staff_pending", "ship_needs_review": False,
                "ship_warnings": ["ยังไม่ได้เปิด Mat ค่าขนส่ง"], "ship_trace": []}

    sel = cart.selected_items
    needs_ship = any(it.supply_mode in ("ship", "install") for it in sel)
    install = Decimal(cart.install_fee or 0) if any(it.supply_mode == "install" or it.requires_install for it in sel) else Decimal(0)
    base = {"install_fee": install, "quoted": cart.delivery_quoted_at is not None, "zone": cart.ship_zone, "postcode": cart.ship_postcode}
    if needs_ship and not cart.ship_postcode:
        # ไม่รู้ปลายทางก็คิดค่าส่งไม่ได้จริง — ตอบ 0 พร้อมเหตุผล ดีกว่าเดาเขตปริยายแล้วโชว์เลขผิด
        return {**base, "shipping_fee": Decimal(0), "ship_source": "no_postcode", "ship_needs_review": False,
                "ship_warnings": ["ยังไม่ได้เลือกปลายทาง — ค่าส่งจะคำนวณหลังเลือกจังหวัด"], "ship_trace": []}
    if shipping_engine.has_rules(db):
        q = shipping_engine.quote(db, cart, cart.ship_postcode, net_total if net_total is not None else Decimal(cart_service.totals(cart)["subtotal"]))
        return {**base, "shipping_fee": q.fee, "ship_source": q.source, "ship_needs_review": q.needs_review, "ship_warnings": q.warnings, "ship_trace": q.trace}
    fee = Decimal(cart.shipping_fee or 0) if needs_ship else Decimal(0)
    return {**base, "shipping_fee": fee, "ship_source": "sap_zone", "ship_needs_review": False, "ship_warnings": [], "ship_trace": []}


def sync_zones(db: Session, zones_json: dict) -> int:
    n = 0
    for pc, z in zones_json["postcodes"].items():
        meta = zones_json["zones"][z]
        row = db.get(DeliveryZone, pc)
        if not row:
            row = DeliveryZone(postcode=pc, zone=z, base_fee=Decimal(meta["base_fee"]), install_fee=Decimal(meta["install_fee"]))
            db.add(row)
            n += 1
        row.zone = z
        row.zone_name = meta["name"]
        row.base_fee = Decimal(meta["base_fee"])
        row.install_fee = Decimal(meta["install_fee"])
        row.lead_days = int(meta["lead_days"])
    db.commit()
    return n
