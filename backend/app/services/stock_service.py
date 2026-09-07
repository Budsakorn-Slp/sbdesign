"""เช็คสต็อก: ยิง SAP สด (timeout 3 วิ + retry 1 ครั้ง) → เขียน stock_checks ทุกครั้ง → fallback stock_cache พร้อม stale=true"""
import logging
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.sap import get_sap_client
from app.integrations.sap.base import SapError, StockRow
from app.models.catalog import Plant, StockCache, StockCheck
from app.models.common import utcnow
from app.models.user import User

log = logging.getLogger("sb.stock")


@dataclass
class StockResult:
    matnr: str
    rows: list[StockRow]
    source: str  # sap | cache
    stale: bool
    fetched_at: datetime
    error: str | None = None


def _call_with_retry(matnr: str) -> list[StockRow]:
    client = get_sap_client()
    last: Exception | None = None
    for attempt in range(2):  # 1 ครั้ง + retry 1 ครั้ง
        try:
            return client.get_stock(matnr)
        except SapError as e:
            last = e
            log.warning("SAP get_stock(%s) attempt %d failed: %s", matnr, attempt + 1, e)
        except Exception as e:  # timeout / network — ถือว่า SAP ล่ม
            last = e
            log.warning("SAP get_stock(%s) attempt %d error: %s", matnr, attempt + 1, e)
    raise SapError(str(last) if last else "SAP unavailable")


def _write_cache(db: Session, rows: list[StockRow]) -> datetime:
    now = utcnow()
    for r in rows:
        row = db.get(StockCache, (r.matnr, r.plant_code))
        if not row:
            row = StockCache(matnr=r.matnr, plant_code=r.plant_code)
            db.add(row)
        row.on_hand = r.on_hand
        row.reserved = r.reserved
        row.atp_date = r.atp_date
        row.fetched_at = now
    return now


def _from_cache(db: Session, matnr: str) -> tuple[list[StockRow], datetime | None]:
    plants = {p.plant_code: p for p in db.scalars(select(Plant)).all()}
    rows = db.scalars(select(StockCache).where(StockCache.matnr == matnr)).all()
    out: list[StockRow] = []
    fetched: datetime | None = None
    for c in rows:
        p = plants.get(c.plant_code)
        out.append(StockRow(matnr=matnr, plant_code=c.plant_code, plant_name=p.name if p else c.plant_code, plant_type=p.type if p else "store", on_hand=c.on_hand, reserved=c.reserved, atp_date=c.atp_date, note="ข้อมูลจาก cache"))
        fetched = c.fetched_at if fetched is None or c.fetched_at > fetched else fetched
    return out, fetched


def check_stock(db: Session, user: User | None, matnr: str) -> StockResult:
    """ทุก call เขียน stock_checks เสมอ พร้อม source (sap|cache)"""
    try:
        rows = _call_with_retry(matnr)
        fetched = _write_cache(db, rows)
        source, stale, err = "sap", False, None
    except SapError as e:
        rows, cached_at = _from_cache(db, matnr)
        fetched = cached_at or utcnow()
        source, stale, err = "cache", True, str(e)
    for r in rows:
        db.add(StockCheck(user_id=user.id if user else None, matnr=matnr, plant_code=r.plant_code, qty_returned=r.available, atp_date=r.atp_date, source=source))
    db.commit()
    return StockResult(matnr=matnr, rows=rows, source=source, stale=stale, fetched_at=fetched, error=err)


def sync_all_stock_to_cache(db: Session, matnrs: list[str]) -> int:
    """ใช้ตอน seed / job รายรอบ: ดึงสต็อกทุกแมทลง cache"""
    n = 0
    client = get_sap_client()
    for matnr in matnrs:
        try:
            _write_cache(db, client.get_stock(matnr))
            n += 1
        except SapError:
            continue
    db.commit()
    return n


def earliest_atp(rows: list[StockRow], qty: int = 1) -> date | None:
    """วันที่พร้อมส่งเร็วสุดที่มีของพอ (ใช้ตอนลงตะกร้า/ออกใบเสนอราคา)"""
    cands = [r.atp_date for r in rows if r.available >= qty and r.atp_date]
    return min(cands) if cands else None


def stale_minutes(fetched_at: datetime) -> int:
    return max(0, int((utcnow() - fetched_at).total_seconds() // 60))


def settings_timeout() -> float:
    return get_settings().sap_timeout_seconds
