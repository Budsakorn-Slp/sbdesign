from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, utcnow, uuid_pk


class UserEvent(Base):
    """พฤติกรรมดิบ — โปรดักชันควร partition ตาม created_at รายเดือน (ดู migration STEP 10)"""

    __tablename__ = "user_events"
    __table_args__ = (Index("ix_user_events_matnr_created", "matnr", "created_at"),)

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    anon_token: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    event: Mapped[str] = mapped_column(String(32), index=True, nullable=False)  # view_material | search | add_to_cart | remove_from_cart | begin_checkout | purchase
    matnr: Mapped[str | None] = mapped_column(String(18), nullable=True)
    query: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="web", nullable=False)  # web | sales_app
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class SearchQuery(Base):
    __tablename__ = "search_queries"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    anon_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    q: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clicked_matnr: Mapped[str | None] = mapped_column(String(18), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class RecentlyViewed(Base):
    __tablename__ = "recently_viewed"
    __table_args__ = (UniqueConstraint("owner_key", "matnr", name="uq_recent_owner_matnr"),)

    id: Mapped[str] = uuid_pk()
    owner_key: Mapped[str] = mapped_column(String(80), index=True, nullable=False)  # "u:<user_id>" หรือ "a:<anon_token>"
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    matnr: Mapped[str] = mapped_column(String(18), nullable=False)
    views: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    viewed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class Wishlist(Base, TimestampMixin):
    __tablename__ = "wishlists"
    __table_args__ = (UniqueConstraint("user_id", "matnr", name="uq_wishlist_user_matnr"),)

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    matnr: Mapped[str] = mapped_column(String(18), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class OrderHistory(Base):
    """mirror ของออร์เดอร์ใน SAP — อ่านอย่างเดียว (ของจริง sync จาก SAP)"""

    __tablename__ = "order_history"

    id: Mapped[str] = uuid_pk()
    so_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    sap_customer_no: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    customer_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    order_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)  # confirmed | in_production | shipping | delivered | cancelled
    channel: Mapped[str] = mapped_column(String(24), default="in_store_assisted", nullable=False)
    branch: Mapped[str | None] = mapped_column(String(60), nullable=True)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    lines: Mapped[list["OrderHistoryLine"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderHistoryLine(Base):
    __tablename__ = "order_history_lines"

    id: Mapped[str] = uuid_pk()
    order_id: Mapped[str] = mapped_column(ForeignKey("order_history.id", ondelete="CASCADE"), index=True, nullable=False)
    matnr: Mapped[str] = mapped_column(String(18), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    order: Mapped[OrderHistory] = relationship(back_populates="lines")


class MaterialDailyStat(Base):
    """สรุปรายวันที่ job สร้าง — ใช้จัดอันดับขายดีโดยไม่ต้องสแกน user_events ทุกครั้ง"""

    __tablename__ = "material_daily_stats"
    __table_args__ = (UniqueConstraint("stat_date", "matnr", name="uq_stat_date_matnr"),)

    id: Mapped[str] = uuid_pk()
    stat_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    matnr: Mapped[str] = mapped_column(String(18), index=True, nullable=False)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    add_to_cart: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    orders: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    qty_sold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)


class BestSeller(Base):
    __tablename__ = "best_sellers"

    matnr: Mapped[str] = mapped_column(String(18), primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    qty_sold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
