from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class AvailabilityItemOut(BaseModel):
    item_id: str | None = None
    matnr: str
    name: str
    qty: int
    status: str  # full | split | short | none | unknown
    label: str
    ready_qty: int
    ready_date: date | None = None
    later_qty: int
    later_date: date | None = None
    short_qty: int
    sap_name: str | None = None
    sap_unit_price: Decimal | None = None
    sap_amount: Decimal | None = None
    sap_discount_percent: float | None = None
    our_amount: Decimal | None = None
    price_diff: Decimal | None = None


class AvailabilityOut(BaseModel):
    """ผลเช็คสต็อก — ทั้งตะกร้าในการยิงครั้งเดียว"""

    cart_id: str
    checked_at: datetime
    req_date: date
    customer_no: str
    is_walkin: bool
    source: str  # sap | mock
    all_ok: bool
    message: str
    items: list[AvailabilityItemOut] = []


class AvailabilityOneIn(BaseModel):
    matnr: str = Field(min_length=1, max_length=18)
    qty: int = Field(default=1, ge=1, le=9999)
