"""import ทุก model ที่นี่ เพื่อให้ Alembic autogenerate เห็นครบ"""
from app.models.catalog import Brand, Category, Material, MaterialPrice, Plant, StockCache, StockCheck  # noqa: F401
from app.models.user import OtpCode, User, UserSession  # noqa: F401
