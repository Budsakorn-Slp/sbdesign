from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class PresoIn(BaseModel):
    cart_id: str
    note: str | None = None


class PresoSummaryOut(BaseModel):
    id: str
    preso_no: str
    status: str
    cart_id: str
    customer_name: str | None = None
    customer_tier: str | None = None
    sales_name: str | None = None
    item_count: int
    grand_total: Decimal
    note: str | None = None
    quotation_no: str | None = None
    quotation_status: str | None = None
    updated_at: datetime
    created_at: datetime


class PresoOut(PresoSummaryOut):
    snapshot: dict


class CreateQuotationIn(BaseModel):
    force: bool = False


class QuotationLineOut(BaseModel):
    matnr: str
    sku: str
    name: str
    variant: str | None = None
    qty: int
    unit_price: Decimal
    line_discount: Decimal
    line_total: Decimal
    supply_mode: str
    plant_code: str | None = None
    atp_date: date | None = None
    added_by: str
    requires_install: bool


class QuotationDiscountOut(BaseModel):
    kind: str
    code: str | None = None
    title: str | None = None
    amount: Decimal


class QuotationOut(BaseModel):
    id: str
    quotation_no: str
    preso_no: str | None = None
    status: str
    channel: str
    customer: dict
    sales_name: str | None = None
    sales_code: str | None = None
    lines: list[QuotationLineOut]
    discounts: list[QuotationDiscountOut] = []
    subtotal: Decimal
    discount_total: Decimal
    shipping_fee: Decimal
    install_fee: Decimal
    shipping_discount: Decimal
    vat: Decimal
    grand_total: Decimal
    deposit_amount: Decimal
    valid_until: date
    pdf_url: str | None = None
    ship_address: str | None = None
    ship_postcode: str | None = None
    ship_zone: str | None = None
    slot_date: date | None = None
    slot_period: str | None = None
    stock_warnings: list | None = None
    sap_so_no: str | None = None
    sap_sync_status: str
    sap_sync_error: str | None = None
    issued_at: datetime
    paid_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    link_token: str | None = None  # เฉพาะพนักงาน — ใช้สร้างลิงก์ให้ลูกค้า


class SendIn(BaseModel):
    channel: str = Field(pattern="^(email|sms)$")


class CancelIn(BaseModel):
    reason: str | None = None
