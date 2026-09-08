"""import ทุก model ที่นี่ เพื่อให้ Alembic autogenerate เห็นครบ"""
from app.models.analytics import BestSeller, MaterialDailyStat, OrderHistory, OrderHistoryLine, RecentlyViewed, SearchQuery, UserEvent, Wishlist  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.models.cart import Cart, CartItem, CartItemHistory  # noqa: F401
from app.models.catalog import Brand, Category, Material, MaterialPrice, Plant, StockCache, StockCheck  # noqa: F401
from app.models.consent import Consent, DataRequest  # noqa: F401
from app.models.delivery import DeliverySlot, DeliveryZone, SlotHold  # noqa: F401
from app.models.payment import Payment, SapSyncJob  # noqa: F401
from app.models.promo import AppliedDiscount, Promotion  # noqa: F401
from app.models.quotation import Preso, Quotation, QuotationLine  # noqa: F401
from app.models.user import OtpCode, User, UserSession  # noqa: F401
