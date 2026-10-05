"""เลือก gateway ตามค่า PAYMENT_PROVIDER"""
from functools import lru_cache

from app.core.config import get_settings
from app.integrations.payment.base import ChargeRequest, ChargeResult, PaymentError, PaymentGateway


@lru_cache
def get_payment_gateway() -> PaymentGateway:
    s = get_settings()
    if s.payment_provider == "kbank":
        from app.integrations.payment.kbank import KBankGateway

        return KBankGateway.from_settings(s)
    from app.integrations.payment.mock import MockGateway

    return MockGateway()


def reset_payment_gateway() -> None:
    get_payment_gateway.cache_clear()


__all__ = ["ChargeRequest", "ChargeResult", "PaymentError", "PaymentGateway",
           "get_payment_gateway", "reset_payment_gateway"]
