from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.cart import cart_out
from app.api.deps import require_role
from app.db.session import get_db
from app.integrations.sap.base import SapError
from app.models.catalog import Material
from app.models.user import User
from app.schemas.availability import AvailabilityItemOut, AvailabilityOneIn, AvailabilityOut
from app.schemas.cart import AddItemIn, CartOut, UpdateItemIn
from app.services import availability_service, cart_service, sales_service

router = APIRouter(tags=["sales"])
sales_only = require_role("sales", "manager")


class OpenCartIn(BaseModel):
    label: str | None = Field(default=None, max_length=120)


class AttachIn(BaseModel):
    customer_key: str = Field(min_length=1, description="เลขสมาชิก / เบอร์โทร / อีเมล")


class SalesCartSummary(BaseModel):
    id: str
    no: str
    label: str | None = None
    customer_name: str | None = None
    customer_tier: str | None = None
    sap_customer_no: str | None = None
    count: int
    subtotal: str
    pending_count: int
    expires_at: str | None = None
    updated_at: str


def summary(c) -> SalesCartSummary:
    t = cart_service.totals(c)
    return SalesCartSummary(
        id=c.id, no=c.no, label=c.label, customer_name=c.customer.name if c.customer else None, customer_tier=c.customer.tier if c.customer else None,
        sap_customer_no=c.customer.sap_customer_no if c.customer else None, count=t["count"], subtotal=str(t["subtotal"]), pending_count=t["pending_count"],
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


@router.post("/sales/carts/{cart_id}/attach-customer", response_model=CartOut)
def attach_customer(cart_id: str, body: AttachIn, db: Session = Depends(get_db), me: User = Depends(sales_only)):
    """ผูกลูกค้า — ถ้าลูกค้ามีตะกร้าออนไลน์อยู่จะ merge เข้าใบนี้"""
    cart = sales_service.require_my_cart(db, me, cart_id)
    cart, _ = sales_service.attach_customer(db, me, cart, body.customer_key)
    return cart_out(cart, db)


@router.delete("/sales/carts/{cart_id}/attach-customer", response_model=CartOut)
def detach_customer(cart_id: str, db: Session = Depends(get_db), me: User = Depends(sales_only)):
    cart = sales_service.require_my_cart(db, me, cart_id)
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


@router.get("/customers/search")
def customers_search(q: str = Query(min_length=2), db: Session = Depends(get_db), me: User = Depends(sales_only)):
    """เลขสมาชิก / เบอร์โทร / อีเมล → รายชื่อลูกค้า + จำนวนของในตะกร้าออนไลน์"""
    return sales_service.search_customers(db, me, q)
