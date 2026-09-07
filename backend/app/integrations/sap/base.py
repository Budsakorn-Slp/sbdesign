"""Contract ของ SAP adapter — ทีมหลังบ้านทำ service จริง เราคุยผ่าน interface นี้เท่านั้น
สลับ implementation ด้วย env SAP_MODE=mock|http (ดู app/integrations/sap/__init__.py)
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol


class SapError(Exception):
    """SAP ตอบไม่ได้ / timeout — service ชั้นบนจะ retry แล้ว fallback cache"""


@dataclass
class MaterialDTO:
    matnr: str
    sku: str
    name_th: str
    barcode: str | None = None
    name_en: str | None = None
    variant: str | None = None
    spec: str | None = None
    description: str | None = None
    category_id: str | None = None
    brand_id: str | None = None
    room: str | None = None
    image_url: str | None = None
    requires_install: bool = False
    is_takeaway_ok: bool = True
    is_new: bool = False
    volume_m3: float | None = None
    weight_kg: float | None = None
    tags: list[str] = field(default_factory=list)
    prices: dict[str, float] = field(default_factory=dict)  # tier -> price  (standard, Gold, Silver, compare_at)


@dataclass
class StockRow:
    matnr: str
    plant_code: str
    plant_name: str
    plant_type: str  # store | warehouse
    on_hand: int
    reserved: int
    atp_date: date | None
    note: str | None = None

    @property
    def available(self) -> int:
        return max(0, self.on_hand - self.reserved)


@dataclass
class CartLineDTO:
    matnr: str
    qty: int
    unit_price: Decimal
    category_id: str | None = None
    supply_mode: str = "ship"
    requires_install: bool = False
    volume_m3: float | None = None


@dataclass
class CartDTO:
    cart_id: str
    lines: list[CartLineDTO]
    subtotal: Decimal


@dataclass
class CustomerDTO:
    sap_customer_no: str
    name: str
    tier: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    postcode: str | None = None


@dataclass
class PromoOffer:
    code: str
    title: str
    condition_text: str
    eligible: bool
    amount: Decimal  # ส่วนลดเป็นบาท (0 ถ้าไม่เข้าเงื่อนไข)
    reason: str | None = None  # ทำไมยังไม่เข้าเงื่อนไข / ขาดอะไร
    stackable: bool = True
    discount_type: str = "amount"


@dataclass
class PromoResult:
    eligible: list[PromoOffer]
    ineligible: list[PromoOffer]
    staff_discount_quota_percent: float


@dataclass
class DeliverySlotDTO:
    id: str
    date: date
    period: str  # am | pm
    zone: str
    quota: int
    booked: int

    @property
    def remaining(self) -> int:
        return max(0, self.quota - self.booked)


@dataclass
class DeliveryQuote:
    postcode: str
    zone: str
    zone_name: str
    base_fee: Decimal
    install_fee: Decimal
    total_fee: Decimal
    groups: dict[str, list[str]]  # takeaway / ship / install -> [matnr]
    slots: list[DeliverySlotDTO]


@dataclass
class SapSoResult:
    ok: bool
    sap_so_no: str | None
    message: str | None = None


class SapClient(Protocol):
    def search_materials(self, q: str, limit: int = 20) -> list[MaterialDTO]: ...

    def list_materials(self) -> list[MaterialDTO]: ...

    def get_stock(self, matnr: str) -> list[StockRow]: ...  # ต่อ plant + atp_date

    def evaluate_promotions(self, cart: CartDTO, customer: CustomerDTO | None) -> PromoResult: ...

    def quote_delivery(self, cart: CartDTO, postcode: str) -> DeliveryQuote: ...

    def create_sales_order(self, quotation_no: str) -> SapSoResult: ...

    def get_customer(self, key: str) -> CustomerDTO | None: ...
