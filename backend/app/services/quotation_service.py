"""Preso (ใบร่าง) + Quotation (ล็อกราคา/โปร แล้วส่งต่อ SAP)
- Save Preso: snapshot ตะกร้า + ยอด ณ ตอนนั้น · 1 ตะกร้ามี draft ได้ใบเดียว (save ซ้ำ = อัปเดตใบเดิม)
- สร้าง Quotation: ยิงเช็คสต็อกสดก่อน ถ้าไม่พอเตือน (409) · ตัวเลขทุกตัวมาจาก promo_service.compute_totals ฟังก์ชันเดียวกับตะกร้า
- issued แล้วแก้ไม่ได้ → cancel แล้วออกใหม่
"""
import hashlib
import hmac
import logging
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.cart import Cart
from app.models.common import utcnow
from app.models.delivery import DeliverySlot
from app.models.promo import AppliedDiscount
from app.models.quotation import Preso, Quotation, QuotationLine
from app.models.user import User
from app.services import audit_service, cart_service, catalog_service, delivery_service, promo_service, stock_service
from app.services import relationship_service

log = logging.getLogger("sb.quotation")


# ---------- เลขเอกสาร ----------
def _doc_no(db: Session, model, col, prefix: str) -> str:
    today = utcnow().strftime("%y%m%d")
    n = int(db.scalar(select(func.count()).select_from(model).where(col.like(f"{prefix}-{today}-%"))) or 0) + 1
    while True:
        no = f"{prefix}-{today}-{n:04d}"
        if not db.scalar(select(model.id).where(col == no)):
            return no
        n += 1


# ---------- snapshot ----------
def build_snapshot(db: Session, cart: Cart) -> dict:
    t = promo_service.compute_totals(db, cart)
    slot = delivery_service.slot_of_cart(db, cart)
    return {
        "cart_no": cart.no,
        "customer": ({"id": cart.customer.id, "name": cart.customer.name, "points": cart.customer.points, "sap_customer_no": cart.customer.sap_customer_no, "phone": cart.customer.phone, "email": cart.customer.email} if cart.customer else None),
        "items": [
            {"matnr": it.matnr, "sku": it.sku, "name": it.name_snapshot, "variant": it.variant_snapshot, "qty": it.qty, "unit_price": str(it.unit_price_snapshot), "price_tier": it.price_tier,
             "line_total": str(it.line_total), "supply_mode": it.supply_mode, "plant_code": it.plant_code, "atp_date": it.atp_date.isoformat() if it.atp_date else None, "added_by": it.added_by,
             "requires_install": it.requires_install, "note": it.note}
            for it in cart.selected_items
        ],
        "discounts": [{"kind": l["kind"], "code": l["code"], "title": l["title"], "amount": str(l["amount"]), "status": l["status"], "percent": str(l["percent"]) if l["percent"] is not None else None} for l in t.lines],
        "totals": {"subtotal": str(t.subtotal), "member_savings": str(t.member_savings), "discount_total": str(t.discount_total), "net_total": str(t.net_total), "shipping_fee": str(t.shipping_fee), "install_fee": str(t.install_fee), "shipping_discount": str(t.shipping_discount), "grand_total": str(t.grand_total), "vat_included": str(t.vat_included)},
        "delivery": {"postcode": cart.ship_postcode, "address": cart.ship_address, "zone": cart.ship_zone, "slot_id": cart.slot_id, "slot_date": slot.date.isoformat() if slot else None, "slot_period": slot.period if slot else None},
        "saved_at": utcnow().isoformat(),
    }


# ---------- Preso ----------
def draft_of_cart(db: Session, cart: Cart) -> Preso | None:
    return db.scalar(select(Preso).where(Preso.cart_id == cart.id, Preso.status == "draft"))


# ---------- ด่านก่อนบันทึกใบ PRE ----------
# ลำดับตามผังงานของทีมขาย: ลูกค้า → ข้อมูลลูกค้า → เช็คสต็อก → เช็คโปรฯ → เช็คสต็อกซ้ำ + คิวส่ง
# แต่ละด่านตอบเป็น (ผ่านไหม, บอกให้ทำอะไรต่อ) เพื่อให้หน้าเซลล์เอาไปทำเป็นเช็คลิสต์ได้ตรงๆ
#
# "ข้อมูลลูกค้า" เคยแยกเป็นสองด่าน (ผูกลูกค้า / ชื่อ-เบอร์-ที่อยู่) แต่บนจอมันคือเรื่องเดียวกัน
# และด่านที่สองจะผ่านไม่ได้เลยถ้าด่านแรกยังไม่ผ่าน — พนักงานเห็นสองบรรทัดที่ขยับพร้อมกัน
# เลยยุบเหลือด่านเดียว แล้วให้ข้อความบอกว่าตอนนี้ขาดอะไร (ยังไม่ผูก / ผูกแล้วแต่ขาดที่อยู่)
PRESO_STEPS = ("customer", "stock", "promo", "delivery")

STEP_TITLE = {
    "customer": "ข้อมูลลูกค้า",
    "stock": "เช็คสต็อก",
    "promo": "เช็คโปรโมชั่น",
    "delivery": "คิวจัดส่ง",
}


def preso_steps(db: Session, cart: Cart) -> list[dict]:
    """สถานะแต่ละด่าน เรียงตามลำดับที่ต้องทำ — ด่านที่ยังไม่ถึงคิวจะบอกว่าต้องทำอันก่อนหน้าก่อน"""
    cust = cart.customer
    rev = cart.rev or 0
    checks: dict[str, tuple[bool, str]] = {}

    # ด่านเดียวแต่ขาดได้สองแบบ — ข้อความต้องบอกให้ตรงว่าต้องไปทำอะไร ไม่ใช่แค่ "ยังไม่ครบ"
    missing = [] if not cust else [w for w, ok in (("ชื่อ", bool(cust.name)), ("เบอร์โทร", bool(cust.phone)),
                                                   ("ที่อยู่จัดส่ง", bool(cart.ship_address or cart.ship_postcode))) if not ok]
    if not (cust and cust.sap_customer_no):
        checks["customer"] = (False, "ผูกลูกค้ากับตะกร้าก่อน — ลูกค้าใหม่ต้องสมัครสมาชิกให้ได้เลขลูกค้าก่อน")
    elif missing:
        checks["customer"] = (False, "ยังขาด " + " · ".join(missing))
    else:
        checks["customer"] = (True, f"เลขลูกค้า {cust.sap_customer_no} · ข้อมูลครบ")
    checks["stock"] = (
        (True, "ของครบตามที่เช็คไว้") if cart.stock_ok_rev == rev
        else (False, "เช็คสต็อกใหม่ — ตะกร้าเปลี่ยนหลังเช็คครั้งล่าสุด" if cart.stock_ok_rev is not None else "กดเช็คสต็อกก่อน")
    )
    checks["promo"] = (
        (True, "เช็คโปรฯ แล้ว") if cart.promo_rev == rev
        else (False, "เช็คโปรฯ ใหม่ — ตะกร้าเปลี่ยนหลังเช็คครั้งล่าสุด" if cart.promo_rev is not None else "กดเช็คโปรโมชั่น 1 รอบก่อน (ไม่มีโปรฯ ก็ถือว่าผ่าน)")
    )
    slot = db.get(DeliverySlot, cart.slot_id) if cart.slot_id else None
    checks["delivery"] = (
        (True, f"จองคิว {slot.date.isoformat()} ({slot.period}) แล้ว") if slot
        else (False, "เลือกวันจัดส่งจากคิวที่ว่าง")
    )

    out = []
    blocked = False
    for key in PRESO_STEPS:
        ok, note = checks[key]
        out.append({"key": key, "title": STEP_TITLE[key], "ok": ok, "note": note, "blocked": blocked and not ok})
        if not ok:
            blocked = True
    return out


def preso_ready(db: Session, cart: Cart) -> dict:
    steps = preso_steps(db, cart)
    todo = [s for s in steps if not s["ok"]]
    return {"ready": not todo, "steps": steps, "next": todo[0]["key"] if todo else None,
            "message": "พร้อมบันทึกใบ PRE" if not todo else todo[0]["note"]}


def save_preso(db: Session, cart: Cart, actor: User, note: str | None, force_stock: bool = False) -> Preso:
    if not cart.selected_items:
        raise HTTPException(status_code=400, detail="ตะกร้าว่าง บันทึก Preso ไม่ได้")
    # ลูกค้าสั่งเองออนไลน์: ของตัวโชว์/ฝากขายยังจ่ายออนไลน์ไม่ได้ (ดู online_checkout_blocked_groups)
    # เซลล์ขายได้ตามปกติ เพราะยืนอยู่หน้าร้านกับของจริง — ด่านนี้จึงกันเฉพาะฝั่งลูกค้า
    if actor.role == "customer":
        blocked = [it for it in cart.selected_items if catalog_service.pickup_only(it.matnr)]
        if blocked:
            names = " · ".join(it.name_snapshot for it in blocked[:3]) + (" …" if len(blocked) > 3 else "")
            raise HTTPException(status_code=409, detail={
                "message": f"สินค้าต่อไปนี้ต้องรับที่สาขา ยังสั่งซื้อออนไลน์ไม่ได้: {names}",
                "pickup_only": [{"matnr": it.matnr, "name": it.name_snapshot} for it in blocked],
            })
    # ด่านทั้งห้าใช้กับตะกร้าที่พนักงานถือเท่านั้น (ผังงานหน้าร้าน)
    # ลูกค้าสั่งเองออนไลน์เดินคนละทาง — เลือกของ ใส่ที่อยู่ แล้วจ่ายเลย ไม่มีขั้นกดเช็คสต็อก/โปรฯ
    # Preso คือ "ร่าง" — บันทึกค้างไว้ได้แม้ยังทำไม่ครบทุกด่าน
    #
    # หน้าร้านจริงลูกค้าเดินไปดูของต่อ/ไปกินข้าวกลางคัน พนักงานต้องเก็บใบไว้ก่อน
    # ถ้าบังคับให้ครบห้าด่านถึงจะบันทึกได้ พนักงานจะเสียงานที่ทำมาทั้งหมดเมื่อลูกค้าเดินออก
    #
    # ด่านทั้งห้าไปบังคับที่ "ออกใบเสนอราคา" แทน (ดู create_quotation) ซึ่งเป็นจุดที่
    # เอกสารออกไปถึงมือลูกค้าและส่งเข้า SAP จริง ตรงนั้นขาดอะไรไม่ได้
    if cart.owner_sales_id:
        lacking = [s["key"] for s in preso_steps(db, cart) if not s["ok"]]
        if lacking:
            audit_service.log(db, actor, "preso.save_incomplete", "cart", cart.id, {"lacking": lacking})
    preso = draft_of_cart(db, cart)
    if not preso:
        preso = Preso(preso_no=_doc_no(db, Preso, Preso.preso_no, "PRE"), cart_id=cart.id, sales_user_id=actor.id if actor.is_staff else None, customer_user_id=cart.customer_user_id)
        db.add(preso)
    preso.snapshot_json = build_snapshot(db, cart)
    preso.customer_user_id = cart.customer_user_id
    if note is not None:
        preso.note = note
    preso.updated_at = utcnow()
    audit_service.log(db, actor, "preso.save", "preso", preso.preso_no,
                      {"cart_id": cart.id, "grand_total": preso.snapshot_json["totals"]["grand_total"], "forced_stock": bool(force_stock)})
    db.commit()
    db.refresh(preso)
    return preso


def list_presos(db: Session, user: User, status_filter: str | None, mine: bool) -> list[Preso]:
    stmt = select(Preso).options(selectinload(Preso.customer), selectinload(Preso.sales)).order_by(Preso.updated_at.desc())
    if user.role == "customer":
        stmt = stmt.where(Preso.customer_user_id == user.id)
    elif mine or user.role == "sales":
        stmt = stmt.where(Preso.sales_user_id == user.id)
    if status_filter:
        stmt = stmt.where(Preso.status == status_filter)
    return list(db.scalars(stmt).all())


def get_preso(db: Session, user: User, preso_no: str) -> Preso:
    p = db.scalar(select(Preso).options(selectinload(Preso.customer), selectinload(Preso.sales)).where(Preso.preso_no == preso_no))
    if not p:
        raise HTTPException(status_code=404, detail="ไม่พบ Preso")
    if user.role == "customer" and p.customer_user_id != user.id:
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์ดู Preso นี้")
    if user.role == "sales" and p.sales_user_id != user.id:
        raise HTTPException(status_code=403, detail="Preso นี้ไม่ใช่ของคุณ")
    return p


def reopen_preso(db: Session, sales: User, preso: Preso) -> Cart:
    """ดึง Preso กลับมาทำต่อ: เปิดตะกร้าเดิมเข้าเซสชันของเซลล์ (ต่ออายุ)"""
    if preso.status != "draft":
        raise HTTPException(status_code=400, detail=f"Preso สถานะ {preso.status} เปิดแก้ไม่ได้ (ออกใบเสนอราคาแล้ว ต้อง cancel ก่อน)")
    cart = cart_service.load_cart(db, preso.cart_id)
    if not cart:
        raise HTTPException(status_code=404, detail="ไม่พบตะกร้าของ Preso")
    if cart.owner_sales_id and cart.owner_sales_id != sales.id and cart.is_open:
        raise HTTPException(status_code=409, detail="ตะกร้านี้มีเซลล์คนอื่นถืออยู่")
    cart.status = "open"
    cart.closed_at = None
    cart.owner_sales_id = sales.id
    cart.owner_sales = sales
    cart.expires_at = utcnow() + cart_service.sales_cart_ttl()
    audit_service.log(db, sales, "preso.reopen", "preso", preso.preso_no, {"cart_id": cart.id})
    db.commit()
    return cart_service.load_cart(db, cart.id)


# ---------- Quotation ----------
def live_stock_check(db: Session, cart: Cart, actor: User | None) -> list[dict]:
    """ยิง SAP สดทุกบรรทัด — คืนรายการที่ของไม่พอ"""
    shortages: list[dict] = []
    for it in cart.selected_items:
        res = stock_service.check_stock(db, actor, it.matnr)
        rows = [r for r in res.rows if (not it.plant_code) or r.plant_code == it.plant_code] if it.supply_mode in ("takeaway", "pickup") else res.rows
        avail = sum(r.available for r in rows)
        if avail < it.qty:
            shortages.append({"matnr": it.matnr, "name": it.name_snapshot, "need": it.qty, "available": avail, "plant_code": it.plant_code, "stale": res.stale, "supply_mode": it.supply_mode})
        elif it.supply_mode in ("ship", "install"):
            it.atp_date = stock_service.earliest_atp(res.rows, it.qty) or it.atp_date
    db.commit()
    return shortages


def create_quotation(db: Session, preso: Preso, actor: User, force: bool = False, channel: str = "in_store_assisted") -> Quotation:
    if preso.status != "draft":
        raise HTTPException(status_code=400, detail=f"Preso สถานะ {preso.status} ออกใบเสนอราคาซ้ำไม่ได้")
    cart = cart_service.load_cart(db, preso.cart_id)
    if not cart or not cart.selected_items:
        raise HTTPException(status_code=400, detail="ตะกร้าว่าง")
    if not cart.customer:
        raise HTTPException(status_code=400, detail="ต้องผูกลูกค้าก่อนออกใบเสนอราคา")
    # ด่านทั้งห้าบังคับที่นี่ — Preso บันทึกค้างไว้ได้ แต่เอกสารที่ออกไปถึงมือลูกค้า
    # และส่งเข้า SAP ต้องครบ ไม่งั้นได้ใบที่ราคา/ของ/คิวส่งไม่ตรงความจริง
    if cart.owner_sales_id:
        # ด่าน "stock" ไม่เช็คตรงนี้ — ปล่อยให้ live_stock_check ข้างล่างจัดการแทน
        # เพราะมันยิง SAP สดและบอกได้ว่าขาดตัวไหนกี่ชิ้น (409 + shortages) ซึ่งมีประโยชน์
        # กว่าข้อความ "ยังไม่ได้เช็คสต็อก" เฉยๆ · และ force ก็คุมจุดเดียวไม่ซ้อนกัน
        todo = [s for s in preso_steps(db, cart) if not s["ok"] and s["key"] != "stock"]
        if todo:
            raise HTTPException(status_code=400, detail=f"ยังทำไม่ครบก่อนออกใบเสนอราคา — {todo[0]['note']}")
    needs_ship = any(it.supply_mode in ("ship", "install") for it in cart.selected_items)
    if needs_ship and not cart.ship_postcode:
        raise HTTPException(status_code=400, detail="มีรายการที่ต้องจัดส่ง — กรุณาคำนวณค่าขนส่งและเลือกคิวก่อน")
    pending = [l for l in promo_service.compute_totals(db, cart).lines if l["status"] == "pending_approval"]
    if pending:
        raise HTTPException(status_code=409, detail="มีส่วนลดที่รอผู้จัดการอนุมัติ — รอผลอนุมัติหรือยกเลิกส่วนลดก่อน")
    shortages = live_stock_check(db, cart, actor)
    if shortages and not force:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"message": "สต็อกไม่พอบางรายการ ตรวจสอบก่อนออกเอกสาร (ส่ง force=true เพื่อออกทั้งที่ของไม่พอ)", "shortages": shortages})

    t = promo_service.compute_totals(db, cart)
    slot = delivery_service.slot_of_cart(db, cart)
    s = get_settings()
    q = Quotation(
        quotation_no=_doc_no(db, Quotation, Quotation.quotation_no, "QT"), preso_id=preso.id, cart_id=cart.id, customer_user_id=cart.customer.id, sales_user_id=actor.id if actor.is_staff else None,
        channel=channel, customer_snapshot={"id": cart.customer.id, "name": cart.customer.name, "points": cart.customer.points, "sap_customer_no": cart.customer.sap_customer_no, "phone": cart.customer.phone, "email": cart.customer.email},
        subtotal=t.subtotal, discount_total=t.discount_total, shipping_fee=t.shipping_fee, install_fee=t.install_fee, shipping_discount=t.shipping_discount, vat=t.vat_included, grand_total=t.grand_total,
        deposit_amount=promo_service.q1(t.grand_total * Decimal("0.2")), valid_until=date.today() + timedelta(days=s.quotation_valid_days), ship_address=cart.ship_address, ship_postcode=cart.ship_postcode,
        ship_zone=cart.ship_zone, slot_id=cart.slot_id, slot_date=slot.date if slot else None, slot_period=slot.period if slot else None, stock_warnings=shortages or None,
    )
    db.add(q)
    db.flush()
    q.pdf_url = f"/quotations/{q.quotation_no}/document"
    for i, it in enumerate(cart.selected_items):
        db.add(QuotationLine(quotation_id=q.id, sort=i, matnr=it.matnr, sku=it.sku, name=it.name_snapshot, variant=it.variant_snapshot, qty=it.qty, unit_price=it.unit_price_snapshot, line_discount=Decimal(0), line_total=it.line_total, supply_mode=it.supply_mode, plant_code=it.plant_code, atp_date=it.atp_date, added_by=it.added_by, requires_install=it.requires_install))
    for l in t.lines:  # คัดลอกส่วนลดไปผูกกับ quotation (ล็อกค่า)
        if l["status"] == "applied":
            db.add(AppliedDiscount(cart_id=None, quotation_id=q.id, kind=l["kind"], promo_code=l["code"], title=l["title"], percent=l["percent"], amount=l["amount"], status="applied", applied_by_user_id=actor.id))
    delivery_service.confirm_hold(db, cart)
    preso.status = "quoted"
    preso.snapshot_json = build_snapshot(db, cart)
    cart.status = "converted"
    cart.closed_at = utcnow()
    audit_service.log(db, actor, "quotation.issue", "quotation", q.quotation_no, {"preso_no": preso.preso_no, "grand_total": str(q.grand_total), "shortages": len(shortages)})
    # ปิดการขายได้ = พนักงานคนนี้เป็นเจ้าของลูกค้ารายนี้ (น้ำหนักสูงกว่าแค่เคยคุย)
    if actor.is_staff and cart.customer_user_id:
        relationship_service.record_sale(db, cart.customer_user_id, actor, cart_id=cart.id, doc_no=q.quotation_no)
    db.commit()
    cart_service.emit(cart, "quotation_issued", {"quotation_no": q.quotation_no, "grand_total": str(q.grand_total)})
    return get_quotation(db, q.quotation_no)


def get_quotation(db: Session, no: str) -> Quotation:
    q = db.scalar(select(Quotation).options(selectinload(Quotation.lines), selectinload(Quotation.customer), selectinload(Quotation.sales), selectinload(Quotation.preso)).where(Quotation.quotation_no == no))
    if not q:
        raise HTTPException(status_code=404, detail="ไม่พบใบเสนอราคา")
    return q


def link_token(no: str) -> str:
    return hmac.new(get_settings().jwt_secret.encode(), f"quotation:{no}".encode(), hashlib.sha256).hexdigest()[:32]


def check_access(q: Quotation, user: User | None, token: str | None) -> None:
    if token and hmac.compare_digest(token, link_token(q.quotation_no)):
        return
    if token:
        raise HTTPException(status_code=403, detail="ลิงก์ไม่ถูกต้องหรือหมดอายุ")
    if user is None:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ หรือเปิดจากลิงก์ที่ได้รับ")
    if user.role == "customer" and q.customer_user_id == user.id:
        return
    if user.role == "sales" and q.sales_user_id == user.id:
        return
    if user.role in ("manager", "admin"):
        return
    raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์ดูใบเสนอราคานี้")


def list_quotations(db: Session, user: User) -> list[Quotation]:
    stmt = select(Quotation).options(selectinload(Quotation.customer), selectinload(Quotation.sales)).order_by(Quotation.issued_at.desc())
    if user.role == "customer":
        stmt = stmt.where(Quotation.customer_user_id == user.id)
    elif user.role == "sales":
        stmt = stmt.where(Quotation.sales_user_id == user.id)
    return list(db.scalars(stmt).all())


def send_link(db: Session, q: Quotation, actor: User, channel: str) -> dict:
    """mock ส่งอีเมล/SMS — ลง log แล้วคืนลิงก์"""
    link = f"/q/{q.quotation_no}?t={link_token(q.quotation_no)}"
    to = q.customer_snapshot.get("email") if channel == "email" else q.customer_snapshot.get("phone")
    log.info("[MOCK %s] to=%s quotation=%s link=%s", channel.upper(), to, q.quotation_no, link)
    audit_service.log(db, actor, f"quotation.send_{channel}", "quotation", q.quotation_no, {"to": to})
    db.commit()
    return {"sent": True, "channel": channel, "to": to, "link": link}


def cancel_quotation(db: Session, q: Quotation, actor: User, reason: str | None) -> Quotation:
    if q.status not in ("issued",):
        raise HTTPException(status_code=400, detail=f"ใบเสนอราคาสถานะ {q.status} ยกเลิกไม่ได้")
    q.status = "cancelled"
    q.cancel_reason = reason
    q.cancelled_at = utcnow()
    # เปิดตะกร้า + Preso กลับมาแก้แล้วออกใหม่
    preso = db.get(Preso, q.preso_id)
    if preso:
        preso.status = "draft"
    cart = cart_service.load_cart(db, q.cart_id)
    if cart:
        cart.status = "open"
        cart.closed_at = None
        if actor.is_staff:
            cart.owner_sales_id = actor.id
            cart.owner_sales = actor
            cart.expires_at = utcnow() + cart_service.sales_cart_ttl()
    if q.slot_id:
        slot = db.get(DeliverySlot, q.slot_id)
        hold = delivery_service.active_hold(db, cart) if cart else None
        if hold and hold.confirmed:
            hold.confirmed = False
            hold.expires_at = utcnow() + timedelta(minutes=delivery_service.HOLD_MINUTES)
        elif slot and slot.booked > 0 and not hold:
            slot.booked -= 1
    audit_service.log(db, actor, "quotation.cancel", "quotation", q.quotation_no, {"reason": reason})
    db.commit()
    return get_quotation(db, q.quotation_no)
