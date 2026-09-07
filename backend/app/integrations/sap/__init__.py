"""factory: สลับ SAP adapter ด้วย env เดียว SAP_MODE=mock|rfc|http"""
from functools import lru_cache

from app.core.config import get_settings
from app.integrations.sap.base import SapClient, SapError  # noqa: F401


@lru_cache
def get_sap_client() -> SapClient:
    mode = get_settings().sap_mode.lower()
    if mode == "mock":
        from app.integrations.sap.mock import MockSapClient

        return MockSapClient()
    if mode == "rfc":
        from app.integrations.sap.rfc import RfcSapClient

        return RfcSapClient.from_settings(get_settings())
    if mode == "http":
        from app.integrations.sap.http import HttpSapClient

        return HttpSapClient.from_settings(get_settings())
    raise RuntimeError(f"SAP_MODE ไม่รู้จัก: {mode} (ใช้ mock | rfc | http)")


def reset_sap_client() -> None:
    get_sap_client.cache_clear()
