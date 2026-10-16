"""factory: สลับ SAP adapter ด้วย env เดียว SAP_MODE=mock|http"""
from functools import lru_cache

from app.core.config import get_settings
from app.integrations.sap.base import SapClient, SapError  # noqa: F401


@lru_cache
def get_sap_client() -> SapClient:
    mode = get_settings().sap_mode.lower()
    if mode == "mock":
        from app.integrations.sap.mock import MockSapClient

        return MockSapClient()
    if mode == "http":
        from app.integrations.sap.http import HttpSapClient

        return HttpSapClient.from_settings(get_settings())
    raise RuntimeError(f"SAP_MODE ไม่รู้จัก: {mode} (ใช้ mock | http)")


def reset_sap_client() -> None:
    get_sap_client.cache_clear()


def lookup_customer(key: str):
    """หาลูกค้าหนึ่งรายจากเบอร์ / อีเมล / เลขลูกค้า — จุดเดียวที่ทั้งระบบใช้ถามทะเบียนลูกค้า

    เปิด SAP_CUSTOMER_URL ไว้ = ถามทะเบียนจริงใน SAP CRM · ว่าง = ข้อมูลจำลองเดิม
    แยกจาก SAP_MODE เพราะส่วนอื่น (โปร/ประวัติสั่งซื้อ) ยังเป็น mock อยู่
    """
    from app.integrations.sap import customer_crm

    if customer_crm.enabled():
        return customer_crm.get_customer(key)
    return get_sap_client().get_customer(key)


def search_customers(key: str) -> list:
    """ทุกรายที่ตรง (ให้พนักงานเลือก) — ทะเบียนจริงเรียงเจ้าของเบอร์ขึ้นก่อน"""
    from app.integrations.sap import customer_crm

    if customer_crm.enabled():
        return customer_crm.search(key)
    c = get_sap_client().get_customer(key)
    return [c] if c else []
