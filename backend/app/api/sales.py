from fastapi import APIRouter, Depends, HTTPException, Query, status
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.cart import cart_out
from app.api.deps import require_role
from app.db.session import get_db
from app.integrations.sap.base import SapError
from app.models.catalog import Material
from app.models.user import User
from app.schemas.availability import AvailabilityBatchIn, AvailabilityItemOut, AvailabilityOneIn, AvailabilityOut
from app.schemas.cart import AddItemIn, CartOut, SelectIn, UpdateItemIn
from app.services import availability_service, cart_service, relationship_service, sales_service, staff_shipping_service

router = APIRouter(tags=["sales"])
sales_only = require_role("sales", "manager")


class OpenCartIn(BaseModel):
    label: str | None = Field(default=None, max_length=120)


class ShippingChargeIn(BaseModel):
    """ค่าขนส่งที่พนักงานยืนยัน — ตัวเลขที่เสนอแก้ทับได้ เพราะหน้าสาขาเจอเคสนอกกฎเสมอ
    (ของชิ้นใหญ่ ต่างจังหวัดไกล ลูกค้าต่อรอง) แต่ต้องบันทึกว่าใครแก้ ไว้ตรวจย้อนหลัง"""

    matnr: str = Field(min_length=1, max_length=18, description="A534 หรือ A761")
    fee: Decimal = Field(ge=0, le=1_000_000, description="ค่าขนส่งที่จะเปิดจริง")
    remark: str | None = Field(default=None, max_length=300, description="เหตุผลที่แก้ / หมายเหตุให้คลัง")


class AttachIn(BaseModel):
    customer_key: str = Field(min_length=1, description="เลขสมาชิก / เบอร์โทร / อีเมล")


class JoinIn(BaseModel):
    customer_key: str = Field(min_length=1)
    join_code: str = Field(min_length=1, max_length=32)


class SalesCartSummary(BaseModel):
    id: str
    no: str
    label: str | None = None
    customer_name: str | None = None
    sap_customer_no: str | None = None
    count: int
    subtotal: str
    pending_count: int
    expires_at: str | None = None
    updated_at: str


def summary(c) -> SalesCartSummary:
    t = cart_service.totals(c)
    return SalesCartSummary(
        id=c.id, no=c.no, label=c.label, customer_name=c.customer.name if c.customer else None,         sap_customer_no=c.customer.sap_customer_no if c.customer else None, count=t["count"], subtotal=str(t["subtotal"]), pending_count=t["pending_count"],
        expires_at=c.expires_at.isoformat() if c.expires_at else None, updated_at=c.updated_at.isoformat(),
    )


@router.get("/sales/carts", response_model=list[SalesCartSummary])
def my_carts(db: Session = Depends(get_db), me: User = Depends(sales_only)):
    """ตะกร้าทั้งหมดที่เซลล์ถืออยู่ (แท็บ)"""
    return [summary(c) for c in sales_service.list_my_carts(db, me)]


@router.post("/sales/carts", response_model=CartOut, status_code=201)
def open_cart(body: OpenCartIn, db: Session = Depends(get_db), me: User = Depends(sales_only)):
    return cart_out(sales_service.open_cart(db, me, body.label), db)


@router.get("/sales/carts/{cart_id}", response_model=CartOut)
def get_cart(cart_id: str, db: Session = Depends(get_db), me: User = Depends(sales_only)):
    return cart_out(sales_service.require_my_cart(db, me, cart_id), db)


@router.delete("/sales/carts/{cart_id}")
def close_cart(cart_id: str, db: Session = Depends(get_db), me: User = Depends(sales_only)):
    cart = sales_service.require_my_cart(db, me, cart_id)
    if cart.owner_sales_id != me.id:   # คนร่วมดูแลกดปิด = ออกจากการดูแล ไม่ใช่ปิดตะกร้าของเพื่อน
        return sales_service.leave_cart(db, me, cart)
    return sales_service.close_cart(db, me, cart)


@router.post("/sales/carts/{cart_id}/items", response_model=CartOut, status_code=201)
def add_item(cart_id: str, body: AddItemIn, db: Session = Depends(get_db), me: User = Depends(sales_only)):
    """เพิ่มของแทนลูกค้า → added_by='sales', pending_ack=true (ถ้าผูกลูกค้าแล้ว)"""
    cart = sales_service.require_my_cart(db, me, cart_id)
    cart_service.add_item(db, cart, me, body.matnr, body.qty, body.supply_mode, body.plant_code, body.note)
    sales_service.touch(db, cart)
    return cart_out(cart_service.load_cart(db, cart.id), db)


@router.patch("/sales/carts/{cart_id}/items/{item_id}", response_model=CartOut)
def update_item(cart_id: str, item_id: str, body: UpdateItemIn, db: Session = Depends(get_db), me: User = Depends(sales_only)):
    cart = sales_service.require_my_cart(db, me, cart_id)
    cart_service.update_item(db, cart, me, item_id, body.qty, body.supply_mode, body.plant_code, body.note)
    sales_service.touch(db, cart)
    return cart_out(cart_service.load_cart(db, cart.id), db)


@router.delete("/sales/carts/{cart_id}/items/{item_id}", response_model=CartOut)
def remove_item(cart_id: str, item_id: str, db: Session = Depends(get_db), me: User = Depends(sales_only)):
    cart = sales_service.require_my_cart(db, me, cart_id)
    cart_service.remove_item(db, cart, me, item_id)
    return cart_out(cart_service.load_cart(db, cart.id), db)


@router.post("/sales/carts/{cart_id}/select", response_model=CartOut)
def select_items(cart_id: str, body: SelectIn, db: Session = Depends(get_db), me: User = Depends(sales_only)):
    """ติ๊กเลือกรายการที่จะคิดเงินในใบนี้ — ไม่ส่ง item_ids = ทั้งตะกร้า

    หน้าเว็บลูกค้ามีช่องติ๊กมาตั้งแต่แรก แต่หน้าขายไม่มี ของที่ลูกค้าไม่ได้ติ๊กจึงหลุดจาก
    ยอดบิลโดยพนักงานมองไม่เห็นและแก้ไม่ได้ ต้องมีช่องติ๊กฝั่งนี้ด้วย
    """
    cart = sales_service.require_my_cart(db, me, cart_id)
    cart_service.set_selected(db, cart, me, body.item_ids, body.selected)
    sales_service.touch(db, cart)
    return cart_out(cart_service.load_cart(db, cart.id), db)


@router.post("/sales/carts/{cart_id}/attach-customer", response_model=CartOut)
def attach_customer(cart_id: str, body: AttachIn, db: Session = Depends(get_db), me: User = Depends(sales_only)):
    """ผูกลูกค้า — ถ้าลูกค้ามีตะกร้าออนไลน์อยู่จะ merge เข้าใบนี้"""
    cart = sales_service.require_my_cart(db, me, cart_id)
    cart, _ = sales_service.attach_customer(db, me, cart, body.customer_key)
    return cart_out(cart, db)


@router.post("/sales/carts/join", response_model=CartOut)
def join_cart(body: JoinIn, db: Session = Depends(get_db), me: User = Depends(sales_only)):
    """เข้าร่วมดูแลตะกร้าที่เพื่อนถือลูกค้ารายนี้อยู่ (ใส่รหัสเข้าร่วม)"""
    return cart_out(sales_service.join_cart(db, me, body.customer_key, body.join_code), db)


@router.delete("/sales/carts/{cart_id}/attach-customer", response_model=CartOut)
def detach_customer(cart_id: str, db: Session = Depends(get_db), me: User = Depends(sales_only)):
    cart = sales_service.require_my_cart(db, me, cart_id)
    sales_service.require_owner(cart, me, "ถอดลูกค้า")
    return cart_out(sales_service.detach_customer(db, me, cart), db)


@router.post("/sales/carts/{cart_id}/availability", response_model=AvailabilityOut)
def check_availability(cart_id: str, db: Session = Depends(get_db), me: User = Depends(sales_only)):
    """เช็คสต็อกกับ SAP ทั้งตะกร้าในการยิงครั้งเดียว (ยิงทีละชิ้นจะเห็นของซ้ำแล้วขายเกิน)"""
    cart = sales_service.require_my_cart(db, me, cart_id)
    try:
        res = availability_service.check_cart(db, cart, me)
    except SapError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"เช็คสต็อกไม่ได้: {e}")
    return AvailabilityOut(**{**vars(res), "items": [AvailabilityItemOut(**vars(i)) for i in res.items]})


@router.post("/sales/availability", response_model=AvailabilityItemOut)
def check_availability_one(body: AvailabilityOneIn, db: Session = Depends(get_db), me: User = Depends(sales_only)):
    """เช็คสินค้าตัวเดียวก่อนใส่ตะกร้า (จากช่องค้นหา)"""
    m = db.get(Material, body.matnr)
    if not m:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้า")
    try:
        return AvailabilityItemOut(**vars(availability_service.check_one(db, m.matnr, body.qty, m.name_th, me)))
    except SapError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"เช็คสต็อกไม่ได้: {e}")


@router.post("/sales/availability/batch", response_model=AvailabilityOut)
def check_availability_batch(body: AvailabilityBatchIn, db: Session = Depends(get_db), me: User = Depends(sales_only)):
    """เช็คหลายรายการพร้อมกันโดยไม่ต้องเปิดตะกร้า — ยิง SAP ครั้งเดียวทั้งชุดเหมือนเช็คตะกร้า

    ให้ช่องทางที่ถือรายการอยู่ในมืออยู่แล้ว (MCP/สคริปต์) เช็คได้โดยไม่ต้องสร้างตะกร้าทิ้งไว้
    ห้ามให้ผู้เรียกวนเรียก /sales/availability ทีละตัวแทน — จะเห็นของชิ้นเดียวกันซ้ำทุกบรรทัด
    """
    try:
        res = availability_service.check_lines(db, [(i.matnr, i.qty) for i in body.items], me, body.customer_no)
    except SapError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"เช็คสต็อกไม่ได้: {e}")
    return AvailabilityOut(**{**vars(res), "items": [AvailabilityItemOut(**vars(i)) for i in res.items]})


@router.get("/customers/search")
def customers_search(q: str = Query(min_length=2), db: Session = Depends(get_db), me: User = Depends(sales_only)):
    """เลขสมาชิก / เบอร์โทร / อีเมล → รายชื่อลูกค้า + จำนวนของในตะกร้าออนไลน์"""
    return sales_service.search_customers(db, me, q)


# ---------- ค่าขนส่งฝั่งพนักงาน (หน้า /sales เท่านั้น ลูกค้าเรียกไม่ได้) ----------
@router.get("/sales/carts/{cart_id}/shipping-charge")
def shipping_charge(cart_id: str, db: Session = Depends(get_db), me: User = Depends(sales_only)):
    """ดูว่าบิลนี้เข้าเทียร์ไหน ควรเปิด Mat ตัวไหน — ยังไม่เขียนอะไรลงตะกร้า"""
    cart = sales_service.require_my_cart(db, me, cart_id)
    return staff_shipping_service.suggest(cart)


# ---------- ลูกค้าคนนี้เป็นของพนักงานคนไหน ----------
def _who(db, uid: str | None) -> dict | None:
    u = db.get(User, uid) if uid else None
    return None if not u else {"id": u.id, "name": u.name, "staff_code": u.staff_code, "branch_id": u.branch_id}


@router.get("/sales/customers/{customer_id}/owner")
def customer_owner(customer_id: str, db: Session = Depends(get_db), _: User = Depends(sales_only)):
    """พนักงานที่ควรดูแลลูกค้ารายนี้ + ประวัติย่อ

    ไม่ได้บังคับว่าใครแตะได้ไม่ได้ — หน้าร้านจริงลูกค้าเดินเข้าหาใครก็ได้ การบล็อกจะทำให้ขายไม่ได้
    หน้าจอเอาไปแสดงว่า "ลูกค้ารายนี้ปกติคุณ X ดูแล" แล้วให้คนหน้างานตัดสินใจเอง
    """
    link = relationship_service.owner_of(db, customer_id)
    return {
        "owner": _who(db, link.sales_user_id) if link else None,
        "attach_count": link.attach_count if link else 0,
        "sale_count": link.sale_count if link else 0,
        "last_at": link.last_at if link else None,
        "last_sale_at": link.last_sale_at if link else None,
        "history": [
            {"kind": e.kind, "sales": _who(db, e.sales_user_id), "doc_no": e.doc_no,
             "note": e.note, "at": e.created_at}
            for e in relationship_service.history_of(db, customer_id, limit=20)
        ],
    }


@router.get("/sales/my-customers")
def my_customers(db: Session = Depends(get_db), me: User = Depends(sales_only)):
    """ลูกค้าในมือของพนักงานคนนี้ — เรียงคนที่ขยับล่าสุดขึ้นก่อน"""
    rows = relationship_service.customers_of(db, me.id)
    return [
        {"customer": _who(db, r.customer_user_id), "attach_count": r.attach_count,
         "sale_count": r.sale_count, "last_at": r.last_at, "last_sale_at": r.last_sale_at,
         "still_mine": (o.sales_user_id == me.id) if (o := relationship_service.owner_of(db, r.customer_user_id)) else False}
        for r in rows
    ]


@router.get("/sales/fleets")
def list_fleets(_: User = Depends(sales_only)):
    """ชุดรถ/ทีมส่งที่ให้เลือกตอนจองคิว — คนละเรตค่าเดินทางกันได้"""
    return staff_shipping_service.fleets()


@router.get("/sales/delivery-extra")
def delivery_extra(province: str = Query(min_length=1), district: str | None = Query(default=None),
                   fleet: str | None = Query(default=None), _: User = Depends(sales_only)):
    """ค่าจัดส่งเพิ่มเติมของปลายทางนี้ = ค่า fleet (กรุงเทพ/ต่างจังหวัด) + ค่าพื้นที่ห่างไกล

    แยกจากเทียร์ Mat เพราะเทียร์ดูยอดบิล ส่วนอันนี้ดูปลายทาง ซึ่งเป็นเรื่องเดียวกับการจัดคิวรถ
    ระบบไม่บวกให้เอง — พนักงานกดบวกเอง บางเคสลูกค้าไปรับเองที่ท่าเรือ/จุดนัด
    """
    return staff_shipping_service.delivery_extra(province, district, fleet)


@router.post("/sales/carts/{cart_id}/shipping-charge", response_model=CartOut)
def set_shipping_charge(cart_id: str, body: ShippingChargeIn, db: Session = Depends(get_db), me: User = Depends(sales_only)):
    cart = sales_service.require_my_cart(db, me, cart_id)
    staff_shipping_service.apply(db, cart, me, body.matnr, body.fee, body.remark)
    sales_service.touch(db, cart)
    return cart_out(cart_service.load_cart(db, cart.id), db)


@router.delete("/sales/carts/{cart_id}/shipping-charge", response_model=CartOut)
def clear_shipping_charge(cart_id: str, role: str = Query(default="tier"),
                          db: Session = Depends(get_db), me: User = Depends(sales_only)):
    # ตรวจกับไฟล์กฎ ไม่ใช่ regex ที่เขียนรายชื่อตายไว้ — เพิ่ม role ใหม่ในไฟล์แล้วลบได้เลย
    known = staff_shipping_service.known_roles()
    if role not in known:
        raise HTTPException(status_code=422, detail=f"ไม่รู้จักบทบาทค่าบริการ '{role}' — มีแค่ {', '.join(known)}")
    cart = sales_service.require_my_cart(db, me, cart_id)
    staff_shipping_service.remove(db, cart, me, role)
    return cart_out(cart_service.load_cart(db, cart.id), db)
