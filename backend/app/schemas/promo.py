from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class OfferOut(BaseModel):
    code: str
    title: str
    condition_text: str
    eligible: bool
    amount: Decimal
    reason: str | None = None
    stackable: bool = True
    discount_type: str = "amount"
    applied: bool = False
    applied_id: str | None = None


class DiscountLineOut(BaseModel):
    id: str
    kind: str
    code: str | None = None
    title: str | None = None
    amount: Decimal
    status: str
    percent: Decimal | None = None


class TotalsOut(BaseModel):
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
    lines: list[DiscountLineOut] = []
    warnings: list[str] = []


class EvaluateIn(BaseModel):
    cart_id: str


class EvaluateOut(BaseModel):
    cart_id: str
    customer_name: str | None = None
    customer_tier: str | None = None
    eligible: list[OfferOut]
    ineligible: list[OfferOut]
    staff_discount_quota_percent: float
    staff_discount: DiscountLineOut | None = None
    totals: TotalsOut


class DiscountIn(BaseModel):
    kind: str = Field(pattern="^(promotion|staff_manual)$")
    promo_code: str | None = None
    percent: Decimal | None = Field(default=None, ge=0, le=50)
    reason: str | None = None


class ApprovalOut(BaseModel):
    id: str
    cart_id: str | None = None
    cart_no: str | None = None
    customer_name: str | None = None
    sales_name: str | None = None
    percent: Decimal | None = None
    amount: Decimal
    reason: str | None = None
    status: str
    created_at: datetime
