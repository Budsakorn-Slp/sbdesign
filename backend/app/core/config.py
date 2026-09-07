from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """ค่า config ทั้งหมดอ่านจาก env (ดู .env.example ที่ root)"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SB Sales App API"
    database_url: str = "sqlite:///./sbdesign.db"
    jwt_secret: str = "dev-only-secret-change-me-in-production-please"
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    sap_mode: str = "mock"  # mock | http
    sap_base_url: str = "http://localhost:9000"
    sap_timeout_seconds: float = 3.0
    sales_cart_ttl_hours: int = 4
    staff_discount_quota_percent: float = 3.0
    quotation_valid_days: int = 7
    otp_debug: bool = True
    payment_webhook_secret: str = "payment-webhook-secret"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
