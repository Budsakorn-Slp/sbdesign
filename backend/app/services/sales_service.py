"""โหมดเซลล์: ถือหลายตะกร้า · ค้นหา/ผูกลูกค้า · merge ตะกร้าออนไลน์ของลูกค้าเข้าใบที่ถือ"""
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.integrations.sap import get_sap_client
from app.integrations.sap.base import SapError
from app.models.cart import Cart
from app.models.common import utcnow
from app.models.user import User
from app.services import audit_service, cart_service, relationship_service
from app.services.auth_service import normalize_phone


def list_my_carts(db: Session, sales: User) -> list[Cart]:
    cart_service.expire_stale_sales_carts(db, sales.id)
    return list(
        db.scalars(
            select(Cart).options(selectinload(Cart.items), selectinload(Cart.customer), selectinload(Cart.owner_sales))
            .where(Cart.owner_sales_id == sales.id, Cart.status == "open")
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
    if cart.customer_user_id and cart.customer_user_id != customer.id:
        raise HTTPException(status_code=409, detail="ตะกร้านี้ผูกลูกค้าคนอื่นอยู่แล้ว — ตัดการเชื่อมต่อก่อน")
    other = db.scalar(select(Cart).where(Cart.customer_user_id == customer.id, Cart.status == "open", Cart.owner_sales_id.is_not(None), Cart.owner_sales_id != sales.id, Cart.id != cart.id))
    if other and other.is_open:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ลูกค้ารายนี้มีพนักงานคนอื่นดูแลตะกร้าอยู่")
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
    audit_service.log(db, sales, "sales.attach_customer", "cart", cart.id, {"customer_id": customer.id, "merged_from": merged_from, "moved": moved})
    # จดว่าใครดูแลใคร — ลูกค้าที่เคยซื้อกับพนักงานคนไหน ครั้งหน้าควรได้คนเดิม
    rel = relationship_service.record_attach(db, customer.id, sales, cart_id=cart.id)
    db.commit()
    cart = cart_service.load_cart(db, cart.id)
    touch(db, cart)
    cart_service.emit(cart, "customer_attached", {"customer_name": customer.name, "sales_name": sales.name, "moved": moved})
    return cart, {"customer_id": customer.id, "merged_online_items": moved, **rel}


def detach_customer(db: Session, sales: User, cart: Cart) -> Cart:
    """ตัดการเชื่อมต่อ: ของที่ลูกค้าใส่เองย้ายกลับไปตะกร้าออนไลน์ของลูกค้า · ของที่เซลล์ใส่อยู่ต่อในใบเซลล์"""
    if not cart.customer_user_id:
        return cart
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
    audit_service.log(db, sales, "sales.detach_customer", "cart", cart.id, {"customer_id": customer_id, "returned_items": len(mine)})
    relationship_service.record_release(db, customer_id, sales.id, "detach", cart_id=cart.id)
    db.commit()
    cart = cart_service.load_cart(db, cart.id)
    cart_service.emit(cart, "customer_detached", {"customer_id": customer_id})
    return cart
