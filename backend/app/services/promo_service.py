"""โปรโมชั่น + ส่วนลด: ประเมินผ่าน SapClient (mock/rfc) · ส่วนลดผูกรายตะกร้า · staff ≤ โควตาใช้ได้เลย เกินต้องขออนุมัติ manager
กฎ: ยอดรวมในตะกร้าและใน Quotation ต้องคำนวณจากฟังก์ชันเดียว (compute_totals) เพื่อให้ตรงกันทุกจุด
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.sap import get_sap_client
from app.integrations.sap.base import CartDTO, CartLineDTO, CustomerDTO, PromoOffer, PromoResult, SapError
from app.models.cart import Cart
from app.models.catalog import Material
from app.models.common import utcnow
from app.models.promo import AppliedDiscount, Promotion
from app.models.user import User
from app.services import audit_service, catalog_service, cart_service

ONE = Decimal("1")


def q1(v: Decimal) -> Decimal:
    return Decimal(v).quantize(ONE, rounding=ROUND_HALF_UP)


def cart_dto(db: Session, cart: Cart) -> CartDTO:
    lines: list[CartLineDTO] = []
    for it in cart.selected_items:
        m = db.get(Material, it.matnr)
        lines.append(CartLineDTO(matnr=it.matnr, qty=it.qty, unit_price=it.unit_price_snapshot, category_id=it.category_id, supply_mode=it.supply_mode, requires_install=it.requires_install, volume_m3=float(m.volume_m3) if m and m.volume_m3 is not None else None))
    return CartDTO(cart_id=cart.id, lines=lines, subtotal=cart_service.totals(cart)["subtotal"])


def customer_dto(cart: Cart) -> CustomerDTO | None:
    c = cart.customer
    if not c:
        return None
    return CustomerDTO(sap_customer_no=c.sap_customer_no or c.id, name=c.name, tier=c.tier, phone=c.phone, email=c.email, address=c.default_address, postcode=c.default_postcode)


def evaluate_with_sap(db: Session, cart: Cart, zone: str | None = None) -> PromoResult:
    try:
        client = get_sap_client()
        res = client.evaluate_promotions(cart_dto(db, cart), customer_dto(cart))
    except SapError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"ประเมินโปรโมชั่นไม่ได้ (SAP): {e}")
    res.staff_discount_quota_percent = get_settings().staff_discount_quota_percent
    return res


def active_discounts(db: Session, cart: Cart) -> list[AppliedDiscount]:
    return list(db.scalars(select(AppliedDiscount).where(AppliedDiscount.cart_id == cart.id, AppliedDiscount.status.in_(("applied", "pending_approval"))).order_by(AppliedDiscount.created_at)).all())


@dataclass
class Totals:
    subtotal: Decimal
    standard_subtotal: Decimal
    member_savings: Decimal
    discount_total: Decimal
    net_total: Decimal
    shipping_fee: Decimal = Decimal(0)
    install_fee: Decimal = Decimal(0)
    shipping_discount: Decimal = Decimal(0)
    grand_total: Decimal = Decimal(0)
    vat_included: Decimal = Decimal(0)
    lines: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def compute_totals(db: Session, cart: Cart, promo_result: PromoResult | None = None) -> Totals:
    """ส่วนลดจริง ณ ตอนนี้ — โปรที่ apply ไว้จะถูกประเมินใหม่ตามตะกร้าปัจจุบัน ถ้าไม่เข้าเงื่อนไขแล้วจะเป็น 0 + warning"""
    subtotal = cart_service.totals(cart)["subtotal"]
    standard = Decimal(0)
    for it in cart.selected_items:
        m = catalog_service.get_material(db, it.matnr)
        std = catalog_service.prices_of(m).get("standard", it.unit_price_snapshot) if m else it.unit_price_snapshot
        standard += std * it.qty
    member_savings = max(Decimal(0), standard - subtotal)
    discounts = active_discounts(db, cart)
    lines: list[dict] = []
    warnings: list[str] = []
    total = Decimal(0)
    promo_codes = [d for d in discounts if d.kind == "promotion" and d.status == "applied"]
    offers: dict[str, PromoOffer] = {}
    if promo_codes:
        res = promo_result or evaluate_with_sap(db, cart)
        offers = {o.code: o for o in res.eligible + res.ineligible}
    for d in discounts:
        if d.kind == "promotion":
            o = offers.get(d.promo_code or "")
            amt = q1(o.amount) if o and o.eligible else Decimal(0)
            if o and not o.eligible:
                warnings.append(f"{d.promo_code}: {o.reason}")
            if d.amount != amt:
                d.amount = amt
            lines.append({"id": d.id, "kind": "promotion", "code": d.promo_code, "title": d.title or (o.title if o else d.promo_code), "amount": amt, "status": d.status, "percent": None})
            if d.status == "applied":
                total += amt
        elif d.kind == "staff_manual":
            amt = q1(subtotal * (d.percent or Decimal(0)) / 100)
            if d.amount != amt:
                d.amount = amt
            lines.append({"id": d.id, "kind": "staff_manual", "code": None, "title": f"ส่วนลดพนักงาน {d.percent:g}%" if d.percent is not None else "ส่วนลดพนักงาน", "amount": amt, "status": d.status, "percent": d.percent})
            if d.status == "applied":
                total += amt
    total = min(total, subtotal)
    # ค่าขนส่ง (STEP 7): quote ล่าสุดบนตะกร้า · โปรส่งฟรี (free_shipping) หักจากค่าส่ง ไม่ใช่จากค่าสินค้า
    from app.services import delivery_service  # import ตรงนี้กัน circular import

    # กฎค่าส่ง (ส่งฟรีเมื่อครบ 6,000 / เรตเดียวเมื่อต่ำกว่า) เทียบกับยอดสินค้าหลังหักส่วนลด
    # ไม่รวมค่าส่งเองและไม่รวมส่วนลดค่าส่ง — ตรงกับ package_value_with_discount ของต้นทาง
    ship = delivery_service.shipping_summary(db, cart, subtotal - total)
    shipping_fee, install_fee = ship["shipping_fee"], ship["install_fee"]
    warnings.extend(ship.get("ship_warnings") or [])
    shipping_discount = Decimal(0)
    for line in lines:
        if line["kind"] == "promotion" and line["status"] == "applied":
            o = offers.get(line["code"] or "")
            if o and o.eligible and (o.code or "").endswith("FREESHIP"):
                shipping_discount += min(shipping_fee, line["amount"])
                total -= line["amount"]  # ไม่หักซ้ำจากค่าสินค้า
                line["title"] = f"{line['title']} (หักจากค่าส่ง)"
                line["amount"] = min(shipping_fee, line["amount"])
    total = max(Decimal(0), total)
    net = subtotal - total
    grand = net + shipping_fee + install_fee - shipping_discount
    vat = q1(grand * 7 / 107)
    if db.dirty:
        db.commit()
    return Totals(subtotal=subtotal, standard_subtotal=standard, member_savings=member_savings, discount_total=total, net_total=net, shipping_fee=shipping_fee, install_fee=install_fee, shipping_discount=shipping_discount, grand_total=grand, vat_included=vat, lines=lines, warnings=warnings)


def apply_promotion(db: Session, cart: Cart, actor: User | None, code: str) -> AppliedDiscount:
    res = evaluate_with_sap(db, cart)
    offer = next((o for o in res.eligible if o.code == code), None)
    if not offer:
        bad = next((o for o in res.ineligible if o.code == code), None)
        raise HTTPException(status_code=400, detail=bad.reason if bad else f"ไม่รู้จักโปรโมชั่น {code}")
    existing = next((d for d in active_discounts(db, cart) if d.kind == "promotion" and d.promo_code == code), None)
    if existing:
        return existing
    if not offer.stackable:
        for d in active_discounts(db, cart):
            if d.kind == "promotion":
                raise HTTPException(status_code=409, detail=f"{code} ใช้ร่วมกับโปรอื่นไม่ได้")
    d = AppliedDiscount(cart_id=cart.id, kind="promotion", promo_code=code, title=offer.title, amount=q1(offer.amount), status="applied", applied_by_user_id=actor.id if actor else None)
    db.add(d)
    audit_service.log(db, actor, "discount.apply", "cart", cart.id, {"kind": "promotion", "code": code, "amount": str(d.amount)})
    db.commit()
    cart_service.emit(cart, "discount_changed", {"code": code})
    return d


def apply_staff_discount(db: Session, cart: Cart, actor: User, percent: Decimal, reason: str | None) -> AppliedDiscount:
    quota = Decimal(str(get_settings().staff_discount_quota_percent))
    if percent < 0 or percent > 50:
        raise HTTPException(status_code=422, detail="เปอร์เซ็นต์ส่วนลดไม่ถูกต้อง")
    for d in active_discounts(db, cart):
        if d.kind == "staff_manual":
            d.status = "removed"
    if percent == 0:
        db.commit()
        cart_service.emit(cart, "discount_changed", {"staff_percent": 0})
        return AppliedDiscount(cart_id=cart.id, kind="staff_manual", percent=Decimal(0), amount=Decimal(0), status="removed")
    subtotal = cart_service.totals(cart)["subtotal"]
    pending = percent > quota and actor.role != "manager"
    d = AppliedDiscount(cart_id=cart.id, kind="staff_manual", percent=percent, amount=q1(subtotal * percent / 100), status="pending_approval" if pending else "applied", reason=reason, applied_by_user_id=actor.id, approved_by_user_id=actor.id if (not pending and percent > quota) else None, approved_at=utcnow() if (not pending and percent > quota) else None)
    db.add(d)
    audit_service.log(db, actor, "discount.apply", "cart", cart.id, {"kind": "staff_manual", "percent": str(percent), "amount": str(d.amount), "status": d.status})
    db.commit()
    cart_service.emit(cart, "discount_changed", {"staff_percent": str(percent), "status": d.status})
    return d


def remove_discount(db: Session, cart: Cart, actor: User | None, discount_id: str) -> None:
    d = db.get(AppliedDiscount, discount_id)
    if not d or d.cart_id != cart.id or d.status == "removed":
        raise HTTPException(status_code=404, detail="ไม่พบส่วนลด")
    d.status = "removed"
    audit_service.log(db, actor, "discount.remove", "cart", cart.id, {"discount_id": d.id, "kind": d.kind, "code": d.promo_code})
    db.commit()
    cart_service.emit(cart, "discount_changed", {"removed": d.id})


def pending_approvals(db: Session) -> list[AppliedDiscount]:
    return list(db.scalars(select(AppliedDiscount).where(AppliedDiscount.status == "pending_approval").order_by(AppliedDiscount.created_at)).all())


def decide(db: Session, manager: User, discount_id: str, approve: bool) -> AppliedDiscount:
    d = db.get(AppliedDiscount, discount_id)
    if not d or d.status != "pending_approval":
        raise HTTPException(status_code=404, detail="ไม่พบคำขออนุมัติที่รออยู่")
    d.status = "applied" if approve else "rejected"
    d.approved_by_user_id = manager.id
    d.approved_at = utcnow()
    audit_service.log(db, manager, "discount.approve" if approve else "discount.reject", "cart", d.cart_id, {"discount_id": d.id, "percent": str(d.percent), "amount": str(d.amount)})
    db.commit()
    cart = cart_service.load_cart(db, d.cart_id) if d.cart_id else None
    if cart:
        cart_service.emit(cart, "discount_changed", {"approved": approve, "discount_id": d.id})
    return d


def sync_promotions(db: Session, rows: list[dict]) -> int:
    n = 0
    for p in rows:
        row = db.get(Promotion, p["code"])
        if not row:
            row = Promotion(code=p["code"], title=p["title"], discount_type=p["discount_type"], discount_value=Decimal(str(p["discount_value"])))
            db.add(row)
            n += 1
        row.title = p["title"]
        row.condition_text = p.get("condition_text")
        row.condition = p.get("condition")
        row.discount_type = p["discount_type"]
        row.discount_value = Decimal(str(p["discount_value"]))
        row.stackable = bool(p.get("stackable", True))
        row.valid_from = date.fromisoformat(p["valid_from"]) if p.get("valid_from") else None
        row.valid_to = date.fromisoformat(p["valid_to"]) if p.get("valid_to") else None
        row.synced_at = utcnow()
    db.commit()
    return n
