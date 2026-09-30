from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, Field

from app.schemas.catalog import MaterialCard


class TrackIn(BaseModel):
    # หน้าที่เกิด event — page_view ใช้บอกว่าเปิดหน้าไหน
    path: str | None = Field(default=None, max_length=200)
    event: str
    matnr: str | None = None
    query: str | None = None
    source: str = "web"
    payload: dict | None = None
    purpose: str = "service"  # marketing = ต้องมี consent ไม่งั้นเก็บแบบไม่ระบุตัวตน


class OrderLineOut(BaseModel):
    matnr: str
    name: str
    qty: int
    unit_price: Decimal
    line_total: Decimal

    model_config = {"from_attributes": True}


class OrderOut(BaseModel):
    so_no: str
    order_date: date
    status: str
    channel: str
    branch: str | None = None
    grand_total: Decimal
    delivery_date: date | None = None
    synced_at: datetime
    lines: list[OrderLineOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class WishlistOut(BaseModel):
    in_wishlist: bool
    items: list[MaterialCard] = Field(default_factory=list)


class DailyJobOut(BaseModel):
    days: int
    stat_rows: int
    best_sellers: int
    top: list[str]
