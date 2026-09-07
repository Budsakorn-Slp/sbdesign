from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.cart import CartCtx
from app.services import delivery_service

router = APIRouter(tags=["delivery"])


class QuoteIn(BaseModel):
    cart_id: str
    postcode: str = Field(min_length=5, max_length=5)
    address: str | None = None


class SlotOut(BaseModel):
    id: str
    date: str
    period: str
    zone: str
    quota: int
    booked: int
    remaining: int
    held_by_this_cart: bool


class GroupItemOut(BaseModel):
    matnr: str
    name: str
    qty: int
    plant_code: str | None = None


class GroupOut(BaseModel):
    mode: str
    label: str
    items: list[GroupItemOut]
    fee_note: str | None = None


class QuoteOut(BaseModel):
    cart_id: str
    postcode: str
    zone: str
    zone_name: str
    base_fee: Decimal
    install_fee: Decimal
    total_fee: Decimal
    groups: list[GroupOut]
    slots: list[SlotOut]
    held_slot_id: str | None = None


class HoldIn(BaseModel):
    cart_id: str


class HoldOut(BaseModel):
    slot_id: str
    expires_at: datetime
    remaining: int


@router.post("/delivery/quote", response_model=QuoteOut)
def quote(body: QuoteIn, ctx: CartCtx = Depends()):
    """{cart_id, postcode} → ค่าขนส่งตามเขต + แยกกลุ่ม ยกกลับ/ส่ง/ติดตั้ง + slot ว่าง"""
    cart = ctx.by_id(body.cart_id)
    return delivery_service.quote(ctx.db, cart, ctx.user, body.postcode, body.address)


@router.post("/delivery/slots/{slot_id}/hold", response_model=HoldOut)
def hold(slot_id: str, body: HoldIn, ctx: CartCtx = Depends()):
    """จองคิวชั่วคราว 15 นาที — คิวเต็มได้ 409"""
    cart = ctx.by_id(body.cart_id)
    return delivery_service.hold_slot(ctx.db, cart, ctx.user, slot_id)


@router.post("/delivery/slots/{slot_id}/release")
def release(slot_id: str, body: HoldIn, ctx: CartCtx = Depends()):
    cart = ctx.by_id(body.cart_id)
    delivery_service.release_hold(ctx.db, cart, ctx.user)
    return {"released": True}
