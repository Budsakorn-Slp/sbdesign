"""โหมดเซลล์: ถือหลายตะกร้า · ค้นหา/ผูกลูกค้า · merge ตะกร้าออนไลน์ของลูกค้าเข้าใบที่ถือ"""
import hmac
import logging

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.integrations.sap import get_sap_client
from app.integrations.sap.base import SapError
from app.models.cart import Cart, CartHandler
from app.models.common import utcnow
from app.models.user import User
from app.services import audit_service, cart_service, relationship_service
from app.services.auth_service import normalize_phone

log = logging.getLogger("sb.sales")


def _stock_was_ok(cart: Cart) -> bool:
    return cart.stock_ok_rev is not None and cart.stock_ok_rev == (cart.rev or 0)


def _recheck_stock(db: Session, cart: Cart, sales: User) -> None:
    """เช็คสต็อกให้ใหม่เองหลังผูก/ถอดลูกค้า — เฉพาะตะกร้าที่เพิ่งเช็คผ่านไปแล้ว

    เซลล์เช็คไปรอบหนึ่งแล้วผลหายเพราะผูกลูกค้าทีหลัง (ราคาคิดใหม่ตามสิทธิสมาชิก และของ
    ในตะกร้าออนไลน์ของลูกค้าไหลเข้ามา) — การบังคับให้กดใหม่คือให้คนทำงานซ้ำในเรื่องที่
    ระบบถามเองได้ · เป็นคำถามเดียวกับปุ่มเช็คสต็อกเป๊ะๆ (query เฉยๆ ไม่ได้ไปจองของ)
    ของยังครบด่านก็กลับมาเขียวเอง ของไม่ครบก็แดงพร้อมเหตุผลจริง ไม่ได้ปล่อยผ่านให้ฟรี

    ตะกร้าที่ยังไม่เคยเช็คไม่ยิงให้ — คนยังไม่ได้ขอ อย่าไปกวน SAP แทนเขา
    SAP ล่มก็ปล่อยให้ด่านแดงไว้ ห้ามให้ "ผูกลูกค้า" พังเพราะ SAP ล่ม
    """
    from app.services import availability_service

    try:
        availability_service.check_cart(db, cart, sales)
    except SapError as e:
        log.warning("เช็คสต็อกซ้ำหลังผูก/ถอดลูกค้าไม่สำเร็จ (ปล่อยให้ด่านแดงไว้): %s", e)


def list_my_carts(db: Session, sales: User) -> list[Cart]:
    cart_service.expire_stale_sales_carts(db, sales.id)
    return list(
        db.scalars(
            select(Cart).options(selectinload(Cart.items), selectinload(Cart.customer), selectinload(Cart.owner_sales))
            .where(Cart.status == "open", Cart.owner_sales_id.is_not(None),
                   or_(Cart.owner_sales_id == sales.id, Cart.handlers.any(CartHandler.user_id == sales.id)))
            .order_by(Cart.created_at)
        ).all()
    )


def open_cart(db: Session, sales: User, label: str | None) -> Cart:
    cart = cart_service.new_cart(db, owner_sales_id=sales.id, label=label, expires_at=utcnow() + cart_service.sales_cart_ttl())
    audit_service.log(db, sales, "sales.cart_open", "cart", None, {"label": label})
    db.commit()
    return cart_service.load_cart(db, cart.id)


def touch(db: Session, cart: Cart) -> None:
    """ต่ออายุตะกร้าที่เซลล์ถือทุกครั้งที่มีการใช้งาน"""
    if cart.owner_sales_id:
        cart.expires_at = utcnow() + cart_service.sales_cart_ttl()
        db.commit()


def require_my_cart(db: Session, sales: User, cart_id: str) -> Cart:
    cart = cart_service.load_cart(db, cart_id)
    if not cart:
        raise HTTPException(status_code=404, detail="ไม่พบตะกร้า")
    if not cart_service.can_access(cart, sales, None):
        raise HTTPException(status_code=403, detail="ตะกร้านี้ไม่ได้อยู่ในความดูแลของคุณ หรือปิดไปแล้ว")
    return cart


def close_cart(db: Session, sales: User, cart: Cart) -> dict:
    """ปิดตะกร้า/จบเซสชัน → สิทธิ์เซลล์หมดทันที
    - มีลูกค้าผูกอยู่: คืนตะกร้าให้ลูกค้าเป็นตะกร้าออนไลน์ของเขาต่อ (ของไม่หาย)
    - ไม่มีลูกค้า: abandoned
    """
    if cart.customer_user_id:
        cart.owner_sales = None
        cart.owner_sales_id = None
        cart.expires_at = None
        for it in cart.items:
            it.pending_ack = False if it.added_by == "customer" else it.pending_ack
        outcome = "returned_to_customer"
    else:
        cart.status = "abandoned"
        cart.closed_at = utcnow()
        outcome = "abandoned"
    audit_service.log(db, sales, "sales.cart_close", "cart", cart.id, {"outcome": outcome})
    db.commit()
    cart_service.emit(cart, "session_closed", {"outcome": outcome})
    return {"cart_id": cart.id, "outcome": outcome}


# ---------- ลูกค้า ----------
def search_customers(db: Session, actor: User, q: str, limit: int = 10) -> list[dict]:
    """ค้นจากเลขสมาชิก / เบอร์โทร / อีเมล ในฐานเรา + SAP (mock) เป็น fallback · เขียน audit customer.view (PDPA)"""
    ql = q.strip()
    digits = normalize_phone(ql)
    conds = [User.sap_customer_no.ilike(f"%{ql}%"), User.email.ilike(f"%{ql.lower()}%"), User.name.ilike(f"%{ql}%")]
    if digits:
        conds.append(User.phone.ilike(f"%{digits}%"))
    users = db.scalars(select(User).where(User.role == "customer", or_(*conds)).limit(limit)).all()
    out: list[dict] = []
    seen: set[str] = set()
    for u in users:
        seen.add(u.sap_customer_no or u.id)
        out.append(_customer_row(db, u))
    if len(out) < limit:
        try:
            sap_c = get_sap_client().get_customer(ql)
        except SapError:
            sap_c = None
        if sap_c and sap_c.sap_customer_no not in seen:
            out.append({"id": None, "name": sap_c.name, "points": sap_c.points, "sap_customer_no": sap_c.sap_customer_no, "phone": sap_c.phone, "email": sap_c.email, "address": sap_c.address, "postcode": sap_c.postcode, "online_cart_count": 0, "source": "sap"})
    audit_service.log(db, actor, "customer.search", "user", None, {"q": ql, "results": len(out)})
    db.commit()
    return out


def _customer_row(db: Session, u: User) -> dict:
    online = db.scalar(select(Cart).options(selectinload(Cart.items)).where(Cart.customer_user_id == u.id, Cart.status == "open", Cart.owner_sales_id.is_(None)))
    return {
        "id": u.id, "name": u.name, "points": u.points, "sap_customer_no": u.sap_customer_no, "phone": _mask_phone(u.phone), "email": u.email, "address": u.default_address,
        "postcode": u.default_postcode, "online_cart_count": sum(it.qty for it in online.items) if online else 0, "source": "local",
    }


def _mask_phone(p: str | None) -> str | None:
    if not p or len(p) < 7:
        return p
    return f"{p[:3]}-xxx-{p[-4:]}"


def resolve_customer(db: Session, key: str) -> User:
    """หา user ลูกค้าจาก key; ถ้ามีเฉพาะใน SAP ให้สร้าง record ลูกค้า (ไม่มีรหัสผ่าน) เพื่อผูกตะกร้า"""
    from app.services.auth_service import find_customer_by_identifier

    u = find_customer_by_identifier(db, key)
    if u:
        return u
    try:
        c = get_sap_client().get_customer(key)
    except SapError:
        c = None
    if not c:
        raise HTTPException(status_code=404, detail="ไม่พบลูกค้า (เลขสมาชิก / เบอร์โทร / อีเมล)")
    u = db.scalar(select(User).where(User.sap_customer_no == c.sap_customer_no))
    if not u:
        u = User(role="customer", name=c.name, phone=normalize_phone(c.phone or "") or None, email=(c.email or "").lower() or None, sap_customer_no=c.sap_customer_no, points=c.points, is_guest=False,
                 default_address=c.address, default_postcode=c.postcode, sap_address=c.address, sap_postcode=c.postcode)
        db.add(u)
        db.commit()
    return u


def attach_customer(db: Session, sales: User, cart: Cart, customer_key: str) -> tuple[Cart, dict]:
    customer = resolve_customer(db, customer_key)
    was_ok = _stock_was_ok(cart)  # ต้องอ่านก่อนแตะตะกร้า
    if cart.customer_user_id and cart.customer_user_id != customer.id:
        raise HTTPException(status_code=409, detail="ตะกร้านี้ผูกลูกค้าคนอื่นอยู่แล้ว — ตัดการเชื่อมต่อก่อน")
    other = db.scalar(select(Cart).where(Cart.customer_user_id == customer.id, Cart.status == "open", Cart.owner_sales_id.is_not(None), Cart.owner_sales_id != sales.id, Cart.id != cart.id))
    if other and other.is_open:
        # บอกให้ชัดว่าใครดูแลอยู่ — พนักงานจะได้ไปขอรหัสเข้าร่วม แทนที่จะเดาเอาเอง
        # บอกชื่อกับสาขาของคนที่ดูแลอยู่ (ไม่บอกรหัส) — ต้องไปขอรหัสพนักงานจากเจ้าตัวมาใส่ถึงเข้าร่วมได้
        # เป็นการยืนยันว่าคุยกันแล้ว ไม่ใช่ใครก็กดแย่งตะกร้าเพื่อนได้
        o = other.owner_sales
        who = (f"{o.name}" + (f" ({o.branch_name})" if o.branch_name else "")) if o else "พนักงานอีกคน"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
            "message": f"ลูกค้ารายนี้อยู่ในความดูแลของ {who} — ขอรหัสพนักงานจากเจ้าตัวเพื่อเข้าร่วมดูแลตะกร้าเดียวกัน",
            "code": "cart_owned_by_other",
            "owner_name": o.name if o else None, "owner_branch": o.branch_name if o else None,
            "cart_no": other.no, "customer_key": customer_key,
        })
    cart.customer = customer
    cart.customer_user_id = customer.id
    cart.label = customer.name
    # ของที่เซลล์ใส่ไว้ก่อนผูกลูกค้า เข้าตะกร้าลูกค้าได้เลย ไม่ต้องให้กดยืนยันทีละชิ้น
    # (ลูกค้าหน้าร้านส่วนใหญ่เดินดูของแล้วให้พนักงานกดใส่ให้จากแท็บเล็ต การบังคับกดรับ
    #  ทีละชิ้นบนมือถือตัวเองคือความยุ่งยากที่ไม่ได้ช่วยอะไร — ยังลบเองได้ตลอดถ้าไม่เอา
    #  และทุกแถวติดป้ายบอกอยู่แล้วว่าใครเป็นคนเพิ่มและเพิ่มตอนไหน)
    for it in cart.items:
        it.pending_ack = False
        # ของที่ลูกค้าเคยไม่ติ๊กไว้บนเว็บ ต้องติ๊กให้หมดตอนพนักงานรับดูแล
        # ไม่งั้นมันเงียบหายจากยอดบิลโดยที่พนักงานไม่รู้ว่าทำไมยอดไม่ตรงกับของตรงหน้า
        it.selected = True
    cart_service.reprice(db, cart)  # ราคาตาม tier ลูกค้า
    db.commit()
    merged_from = None
    moved = 0
    online = db.scalar(select(Cart).options(selectinload(Cart.items)).where(Cart.customer_user_id == customer.id, Cart.status == "open", Cart.owner_sales_id.is_(None), Cart.id != cart.id))
    if online:
        moved = sum(it.qty for it in online.items)
        merged_from = online.id
        cart_service.merge_carts(db, online, cart, sales)
    # ราคาเพิ่งคิดใหม่ตามสิทธิสมาชิก → ผลเช็คโปรฯ รอบก่อนคิดจากราคาที่ไม่ใช่ราคาจริงของ
    # ลูกค้าคนนี้ ต้องหมดอายุด้วย ไม่ใช่แค่ตอนมีของยกเข้ามา (merge_carts เดินเลขให้แล้ว
    # ตอนมีของเข้า — ตรงนี้จึงเดินเฉพาะตอนที่มันไม่ได้เดิน แค่เปลี่ยนคำอธิบายให้ตรงเรื่อง)
    if moved:
        cart.rev_note = f"ผูกลูกค้าแล้วยกของจากตะกร้าลูกค้าเข้ามา {moved} รายการ"
    else:
        cart_service.bump_rev(cart, "ผูกลูกค้า — ราคาคิดใหม่ตามสิทธิสมาชิก")
    audit_service.log(db, sales, "sales.attach_customer", "cart", cart.id, {"customer_id": customer.id, "merged_from": merged_from, "moved": moved})
    # จดว่าใครดูแลใคร — ลูกค้าที่เคยซื้อกับพนักงานคนไหน ครั้งหน้าควรได้คนเดิม
    rel = relationship_service.record_attach(db, customer.id, sales, cart_id=cart.id)
    db.commit()
    if was_ok:
        _recheck_stock(db, cart, sales)
    cart = cart_service.load_cart(db, cart.id)
    touch(db, cart)
    cart_service.emit(cart, "customer_attached", {"customer_name": customer.name, "sales_name": sales.name, "moved": moved})
    return cart, {"customer_id": customer.id, "merged_online_items": moved, **rel}


def detach_customer(db: Session, sales: User, cart: Cart) -> Cart:
    """ตัดการเชื่อมต่อ: ของที่ลูกค้าใส่เองย้ายกลับไปตะกร้าออนไลน์ของลูกค้า · ของที่เซลล์ใส่อยู่ต่อในใบเซลล์"""
    if not cart.customer_user_id:
        return cart
    was_ok = _stock_was_ok(cart)
    customer_id = cart.customer_user_id
    mine = [it for it in cart.items if it.added_by == "customer"]
    if mine:
        back = cart_service.new_cart(db, customer_user_id=customer_id, label=cart.label)
        db.flush()
        for it in mine:
            cart.items.remove(it)
            back.items.append(it)  # ต้อง re-parent ผ่าน relationship ไม่งั้น delete-orphan จะลบทิ้ง
    cart.customer = None
    cart.customer_user_id = None
    cart.label = None
    for it in cart.items:
        it.pending_ack = False
    cart_service.reprice(db, cart)
    # ถอดลูกค้า = ราคากลับไปเป็นราคาปกติ และของที่ลูกค้าใส่เองย้ายออกไป — เช็คใหม่ทั้งคู่
    cart_service.bump_rev(cart, f"ถอดลูกค้าออก — ราคากลับเป็นราคาปกติ{f' · ของลูกค้าย้ายออก {len(mine)} รายการ' if mine else ''}")
    audit_service.log(db, sales, "sales.detach_customer", "cart", cart.id, {"customer_id": customer_id, "returned_items": len(mine)})
    relationship_service.record_release(db, customer_id, sales.id, "detach", cart_id=cart.id)
    db.commit()
    if was_ok:
        _recheck_stock(db, cart, sales)
    cart = cart_service.load_cart(db, cart.id)
    cart_service.emit(cart, "customer_detached", {"customer_id": customer_id})
    return cart


# ---------- ร่วมดูแลตะกร้า ----------
def join_cart(db: Session, sales: User, customer_key: str, join_code: str) -> Cart:
    """เข้าร่วมดูแลตะกร้าที่เพื่อนถือลูกค้ารายนี้อยู่ — ต้องใส่รหัสพนักงานของคนที่ดูแลอยู่"""
    customer = resolve_customer(db, customer_key)
    cart = db.scalar(select(Cart).where(Cart.customer_user_id == customer.id, Cart.status == "open",
                                        Cart.owner_sales_id.is_not(None)).order_by(Cart.updated_at.desc()))
    if not cart or not cart.is_open:
        raise HTTPException(status_code=404, detail="ลูกค้ารายนี้ไม่มีตะกร้าที่พนักงานดูแลอยู่")
    owner_code = (cart.owner_sales.staff_code or "") if cart.owner_sales else ""
    if not owner_code or not hmac.compare_digest((join_code or "").strip().upper(), owner_code.upper()):
        audit_service.log(db, sales, "sales.cart_join_denied", "cart", cart.id, {"customer_key": customer_key})
        db.commit()
        raise HTTPException(status_code=403, detail="รหัสพนักงานไม่ตรงกับคนที่ดูแลตะกร้านี้")
    if cart.owner_sales_id != sales.id and not any(h.user_id == sales.id for h in cart.handlers):
        cart.handlers.append(CartHandler(user_id=sales.id))
        audit_service.log(db, sales, "sales.cart_join", "cart", cart.id, {"owner_sales_id": cart.owner_sales_id})
        db.commit()
        cart_service.emit(cart, "handler_joined", {"name": sales.name, "staff_code": sales.staff_code})
    return cart_service.load_cart(db, cart.id)


def leave_cart(db: Session, sales: User, cart: Cart) -> dict:
    """คนร่วมดูแลกดปิด = ออกจากการดูแล ตะกร้ายังอยู่กับเจ้าของ"""
    cart.handlers[:] = [h for h in cart.handlers if h.user_id != sales.id]
    audit_service.log(db, sales, "sales.cart_leave", "cart", cart.id, {})
    db.commit()
    return {"cart_id": cart.id, "outcome": "left"}


def require_owner(cart: Cart, sales: User, what: str) -> None:
    if cart.owner_sales_id != sales.id:
        raise HTTPException(status_code=403, detail=f"{what}ได้เฉพาะพนักงานเจ้าของตะกร้า")
