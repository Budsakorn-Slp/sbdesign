from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """ค่า config ทั้งหมดอ่านจาก env (ดู .env.example ที่ root)"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SB Sales App API"
    database_url: str = "sqlite:///./sbdesign.db"
    # แหล่งข้อมูลสินค้า (ฐานเว็บ sbdesignsquare) — อ่านอย่างเดียว ไม่ใช่ฐานของแอป
    sbweb_database_url: str = ""
    # ฐาน Magento (10.9.12.67) — ต้นทางรูปสินค้า อ่านอย่างเดียว
    # ใส่แยกเป็นตัวๆ ดีกว่าเขียนเป็น URL เพราะรหัสผ่านมี @ อยู่ข้างใน
    # ถ้ายัดลง URL ต้อง %40 ให้ครบทุกตัว พลาดตัวเดียวมันจะตัด host ผิด
    magento_host: str = ""
    magento_port: int = 3306
    magento_user: str = ""
    magento_password: str = ""
    magento_db: str = "magento3"
    magento_database_url: str = ""  # ใส่ตรงนี้แทนก็ได้ ถ้า encode เองแล้ว

    @property
    def magento_url(self) -> str:
        # ตัวแปรแยกมาก่อนเสมอ — MAGENTO_DATABASE_URL เป็นทางเลือกสำรอง
        # ถ้าให้ URL ชนะ บรรทัดเก่าที่ลืมลบจะแอบถูกใช้แทนโดยไม่มีอะไรเตือน
        if not self.magento_host:
            return self.magento_database_url
        url = URL.create(
            "mysql+pymysql",
            username=self.magento_user,
            password=self.magento_password,
            host=self.magento_host,
            port=self.magento_port,
            database=self.magento_db,
            query={"charset": "utf8mb4"},
        )
        # str(URL) ปิดรหัสผ่านเป็น *** — ถ้าใช้ตรงๆ จะกลายเป็นส่ง "***" ไปเป็นรหัสจริง
        return url.render_as_string(hide_password=False)
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
