"""เช็คสต็อกกับ SAP — ZAIBAPI_MATERIAL_AVAILABILITY ผ่าน RFC gateway (HTTP)

ทำไมต้องยิงทั้งตะกร้าครั้งเดียว ไม่ใช่ทีละชิ้น:
SAP จำลองใบสั่งขายทั้งใบ ของชิ้นที่มีจะถูกบรรทัดแรกจองไปก่อน บรรทัดหลังเห็นของน้อยลงตามจริง
ถ้ายิงแยกทีละบรรทัด ทุกบรรทัดจะเห็น "มีของ" เหมือนกันหมดทั้งที่ของมีชิ้นเดียว → ขายเกิน

สิ่งที่เรียนรู้จากการยิงของจริง (สำคัญตอนอ่านค่า):
- AVAILABLE_QUAN = ของที่มีอยู่ตอนนี้ · COMMITTED_QUAN = ของที่จะเข้ามาเพิ่มวัน COMMITTED_DATE
  ที่ส่งได้ทันที = min(AVAILABLE_QUAN, ที่ขอ) — โชว์ตัวเลขดิบไม่ได้ เพราะบางเคสมันตอบมากกว่าที่ขอ
  (ขอ 50 ตอบ 64) ซึ่งเป็นยอดของทั้งก้อนไม่ใช่ยอดที่จองให้บรรทัดนี้
- ยอดที่ยืนยันได้ = ส่งทันที + ที่จะเข้ามา ส่วนที่เหลือคือของขาด
- MATERIAL กลับมาเป็น 18 หลักเติมศูนย์หน้า
- รหัสสินค้าผิดตัวเดียว AI_RETURN_ITEMS ว่างทั้งบิล ไม่ใช่หายแค่ตัวนั้น → ต้องนับแถวเทียบเสมอ
- REQ_QUANTITY = 0 SAP เปลี่ยนเป็น 1 เงียบๆ → กันไว้ที่ฝั่งเรา
"""
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings
from app.integrations.sap.base import SapError

log = logging.getLogger("sb.sap.avail")

MAX_PROBE_LINES = 25  # ตอนไล่หาว่าบรรทัดไหนพัง ยิงทีละบรรทัด — จำกัดไว้กัน SAP โดนถล่ม


@dataclass
class AvailAsk:
    matnr: str
    qty: int


@dataclass
class AvailLine:
    """หนึ่งบรรทัดที่ SAP ตอบกลับ — ยังไม่ตีความ ปล่อยให้ service ชั้นบนสรุปสถานะ"""

    matnr: str
    qty: int
    description: str | None = None
    sales_unit: str | None = None
    unit_price: Decimal = Decimal(0)  # ราคาป้าย ก่อนส่วนลด
    discount: Decimal = Decimal(0)  # เก็บเป็นบวก (SAP ส่งมาเป็นลบ)
    discount_percent: float = 0.0
    amount: Decimal = Decimal(0)  # ยอดสุทธิของบรรทัดนี้ หลังหักส่วนลดแล้ว
    currency: str = "THB"
    available_qty: int = 0
    available_date: date | None = None
    committed_qty: int = 0
    committed_date: date | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None


class AvailabilityClient(Protocol):
    def check(self, asks: list[AvailAsk], customer_no: str, req_date: date) -> list[AvailLine | None]:
        """คืนผลเรียงตรงกับ asks — None = SAP ไม่รู้จักรหัสนี้"""
        ...


def _matnr(raw: str) -> str:
    return (raw or "").lstrip("0") or "0"


def _date(raw: str) -> date | None:
    raw = (raw or "").strip()
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))
    except ValueError:
        return None


def _dec(v) -> Decimal:
    return Decimal(str(v or 0))


def _qty(v) -> int:
    return int(float(v or 0))


def _to_line(row: dict, ask: AvailAsk) -> AvailLine:
    return AvailLine(
        matnr=_matnr(row.get("MATERIAL", "")) or ask.matnr,
        qty=ask.qty,
        description=(row.get("DESCRIPTION") or "").strip() or None,
        sales_unit=(row.get("SALES_UNIT") or "").strip() or None,
        unit_price=_dec(row.get("UNIT_PRICE")),
        discount=abs(_dec(row.get("DISCOUNT"))),
        discount_percent=float(row.get("PERCENTAGE") or 0),
        amount=_dec(row.get("AMOUNT")),
        currency=(row.get("CURRENCY_UNIT") or "THB").strip() or "THB",
        available_qty=_qty(row.get("AVAILABLE_QUAN")),
        available_date=_date(row.get("AVAILABLE_DATE", "")),
        committed_qty=_qty(row.get("COMMITTED_QUAN")),
        committed_date=_date(row.get("COMMITTED_DATE", "")),
        length_cm=row.get("LAENG"),
        width_cm=row.get("BREIT"),
        height_cm=row.get("HOEHE"),
    )


class HttpAvailabilityClient:
    def __init__(self, url: str, api_key: str, s: Settings):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.timeout = s.sap_avail_timeout_seconds
        self.head = {
            "ORDER_TYPE": s.sap_order_type,
            "SALES_ORG": s.sap_sales_org,
            "DISTR_CHAN": s.sap_distr_chan,
            "DIVISION": s.sap_division,
        }

    @classmethod
    def from_settings(cls, s: Settings) -> "HttpAvailabilityClient":
        return cls(s.sap_avail_url, s.sap_api_key, s)

    def _post(self, asks: list[AvailAsk], customer_no: str, req_date: date) -> list[dict]:
        iso = req_date.isoformat()
        body = {
            "params": {
                "AI_PARAMETER": {**self.head, "CUSTOMER": customer_no, "REQ_DATE": iso},
                # qty ต่ำกว่า 1 SAP จะปัดเป็น 1 ให้เอง — บังคับที่นี่จะได้ไม่มีเลขหลอกกลับมา
                "AI_ORDER_ITEMS": [{"MATERIAL": a.matnr, "REQ_QUANTITY": max(1, a.qty), "REQ_DELIVERY": iso} for a in asks],
            }
        }
        try:
            r = httpx.post(self.url, headers={"X-API-Key": self.api_key}, json=body, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise SapError(f"ต่อ SAP ไม่ได้: {e}") from e
        if r.status_code != 200:
            detail = ""
            try:
                detail = r.json().get("error", {}).get("message") or ""
            except Exception:
                detail = r.text[:200]
            raise SapError(f"SAP ตอบ {r.status_code}: {detail}")
        try:
            data = r.json()["data"]
        except Exception as e:
            raise SapError(f"อ่านคำตอบ SAP ไม่ได้: {e}") from e
        msgs = [m for m in (data.get("AI_MESSAGE") or []) if m]
        if msgs:
            log.warning("SAP availability message: %s", msgs)
        return list(data.get("AI_RETURN_ITEMS") or [])

    def check(self, asks: list[AvailAsk], customer_no: str, req_date: date) -> list[AvailLine | None]:
        if not asks:
            return []
        rows = self._post(asks, customer_no, req_date)
        if len(rows) == len(asks):
            # ตรงจำนวน = เชื่อลำดับได้ (SAP ไล่ ORDER_ITEM 000020, 000040, ...)
            # จับคู่ตามตำแหน่งเท่านั้น เพราะ MATERIAL ซ้ำกันได้หลายบรรทัดในบิลเดียว
            return [_to_line(row, ask) for row, ask in zip(rows, asks)]
        # จำนวนไม่ตรง = มีบรรทัดที่ SAP ไม่รับ แล้วมันทิ้งทั้งบิล จับคู่ตามตำแหน่งไม่ได้แล้ว
        # ยิงทีละบรรทัดเพื่อชี้ตัวที่พัง ยอมเสียเวลาในเคสที่ผิดปกติอยู่แล้ว
        log.warning("SAP ตอบ %d แถว แต่ขอไป %d — ไล่ทีละบรรทัด", len(rows), len(asks))
        if len(asks) > MAX_PROBE_LINES:
            raise SapError("SAP ตอบไม่ครบและตะกร้าใหญ่เกินกว่าจะไล่ทีละรายการ — ลองใหม่อีกครั้ง")
        out: list[AvailLine | None] = []
        for a in asks:
            one = self._post([a], customer_no, req_date)
            out.append(_to_line(one[0], a) if one else None)
        return out


class MockAvailabilityClient:
    """ใช้ตอน dev/test — อ่านสต็อกจาก MockSapClient เดิม จะได้ไม่ต้องต่อ SAP จริง"""

    def __init__(self):
        from app.integrations.sap.mock import MockSapClient

        self.sap = MockSapClient()
        self._prices = {m.matnr: m.prices.get("standard", 0) for m in self.sap.list_materials()}

    def check(self, asks: list[AvailAsk], customer_no: str, req_date: date) -> list[AvailLine | None]:
        out: list[AvailLine | None] = []
        left: dict[str, int] = {}
        for a in asks:
            try:
                rows = self.sap.get_stock(a.matnr)
            except SapError:
                out.append(None)  # mock ไม่รู้จักรหัสนี้ = เลียนแบบ SAP ที่ไม่ตอบแถวกลับมา
                continue
            if a.matnr not in left:
                left[a.matnr] = sum(r.available for r in rows)
            ready = min(left[a.matnr], a.qty)  # บรรทัดก่อนหน้าจองไปแล้ว — เหมือน SAP จริงที่คิดทั้งบิล
            left[a.matnr] -= ready
            atp = min([r.atp_date for r in rows if r.atp_date] or [req_date])
            price = Decimal(str(self._prices.get(a.matnr, 0)))
            out.append(
                AvailLine(
                    matnr=a.matnr, qty=a.qty, description=None, sales_unit="KIT",
                    unit_price=price, amount=price * a.qty, available_qty=ready, available_date=atp if ready else None,
                )
            )
        return out


@lru_cache
def get_availability_client() -> AvailabilityClient:
    s = get_settings()
    if s.sap_avail_url and s.sap_api_key:
        return HttpAvailabilityClient.from_settings(s)
    return MockAvailabilityClient()


def reset_availability_client() -> None:
    get_availability_client.cache_clear()
