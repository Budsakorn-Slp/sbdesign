"""จำนวนของสำหรับ "โชว์" ในหน้ารายการสินค้า — อ่าน cache เสมอ ไม่ยิง SAP ตอนเปิดหน้า

ทำไมต้องแยกจาก availability_service:
  availability_service = เช็คตอน "จะขายจริง" ยิงสดทั้งตะกร้าครั้งเดียว ตัดเลขตามจำนวนที่ขอ
  ไฟล์นี้        = เอาไว้โชว์เฉยๆ เก็บยอดดิบทั้งก้อนไว้ให้การ์ดสินค้าอ่าน

SAP ตอบช้าและเป็นระบบหลังบ้านที่ใช้ร่วมทั้งบริษัท จึงห้ามผูกกับการเลื่อนหน้าเว็บของลูกค้าตรงๆ
หน้าเว็บอ่านจากตารางนี้อย่างเดียว ส่วนการเติมข้อมูลเป็นงานเบื้องหลัง (ดู etl/refresh_stock.py)
"""
import hashlib
import logging
import threading
from collections.abc import Callable
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.sap.base import SapError
from app.integrations.sap.material_stock import get_material_stock_client
from app.models.catalog import ProductStock, ProductStockSite
from app.models.common import utcnow
from app.services.availability_service import req_date_for

log = logging.getLogger("sb.availability.cache")


def ttl() -> timedelta:
    return timedelta(minutes=get_settings().stock_cache_ttl_minutes)


def summary_for(db: Session, matnrs: list[str]) -> dict[str, dict]:
    """ยอดที่โชว์ได้ของรหัสชุดนี้ — ตัวที่ไม่มีใน cache จะไม่มี key (หน้าเว็บถือว่า "ยังไม่รู้")"""
    if not matnrs:
        return {}
    rows = db.scalars(select(ProductStock).where(ProductStock.matnr.in_(matnrs), ProductStock.sap_known.is_(True))).all()
    return {
        r.matnr: {"ready_qty": r.ready_qty, "later_qty": r.later_qty, "later_date": r.later_date,
                  "made_to_order": r.made_to_order, "fetched_at": r.fetched_at}
        for r in rows
    }


def stale_matnrs(db: Session, matnrs: list[str]) -> list[str]:
    """รหัสที่ยังไม่เคยเช็ค หรือเช็คไว้นานเกิน TTL แล้ว — เรียงตามเก่าสุดก่อน

    ตัวที่ SAP บอกว่าไม่รู้จักก็ยังอยู่ในรอบถัดไป เผื่อของถูกเปิดขายทีหลัง แต่ไปต่อท้ายคิว
    """
    if not matnrs:
        return []
    cutoff = utcnow() - ttl()
    rows = {r.matnr: r for r in db.scalars(select(ProductStock).where(ProductStock.matnr.in_(matnrs))).all()}
    never = [m for m in matnrs if m not in rows]
    expired = sorted((r for r in rows.values() if r.fetched_at < cutoff), key=lambda r: r.fetched_at)
    return never + [r.matnr for r in expired]


def _write(db: Session, matnr: str, *, ready: int, later: int, later_date: date | None, known: bool,
           now: datetime, mto: bool = False, sites: list | None = None) -> None:
    row = db.get(ProductStock, matnr)
    if not row:
        row = ProductStock(matnr=matnr)
        db.add(row)
    row.ready_qty, row.later_qty, row.later_date = ready, later, later_date
    row.sap_known, row.made_to_order, row.fetched_at = known, mto, now
    if sites is not None:
        _write_sites(db, matnr, sites, now)


def _write_sites(db: Session, matnr: str, sites: list, now: datetime) -> None:
    """ลบของเดิมทิ้งแล้วใส่ชุดใหม่ — ของย้ายสาขา/ขายหมดที่สาขาหนึ่ง แถวเก่าต้องหายไปด้วย
    ถ้า upsert ทับอย่างเดียว สาขาที่ของหมดแล้วจะค้างอยู่บอกว่ายังมีของตลอดไป"""
    db.query(ProductStockSite).filter(ProductStockSite.matnr == matnr).delete(synchronize_session=False)
    for s in sites:
        db.add(ProductStockSite(matnr=matnr, plant_code=s.plant_code, name=s.name,
                                available_qty=s.available, fetched_at=now))


# รหัสที่ไม่ใช่โชว์รูม — ลูกค้าเดินเข้าไปดูของไม่ได้ ไม่ควรโผล่ในรายการ "มีของที่สาขา"
#   1000  ไม่มีชื่อเลย = คลัง
#   9000  ชื่อเป็นชื่อบริษัท = สต็อกระดับบริษัท
# ที่เหลือ (S***, SH**, SO**, STLV) เป็นโชว์รูมจริงและมีชื่อเรียกที่ลูกค้ารู้จัก
NON_STORE_PLANTS = {"1000", "9000"}


def sites_for(db: Session, matnrs: list[str], named_only: bool = True) -> dict[str, list[ProductStockSite]]:
    """สาขาที่มีของ เรียงจากมากไปน้อย

    named_only = เอาเฉพาะแถวที่มีชื่อสาขา · แถวชื่อว่าง (เช่น PLANT 1000) คือคลัง
    ไม่ใช่โชว์รูมที่ลูกค้าเดินเข้าไปดูของได้ เอาไปโชว์จะกลายเป็น "มีของที่ (ว่าง)"
    """
    if not matnrs:
        return {}
    q = select(ProductStockSite).where(ProductStockSite.matnr.in_(matnrs))
    if named_only:
        q = q.where(ProductStockSite.name != "", ProductStockSite.plant_code.not_in(NON_STORE_PLANTS))
    out: dict[str, list[ProductStockSite]] = {}
    for r in db.scalars(q.order_by(ProductStockSite.available_qty.desc(), ProductStockSite.name)).all():
        out.setdefault(r.matnr, []).append(r)
    return out


def refresh_mock(db: Session, matnrs: list[str], on_batch: Callable[[int], None] | None = None) -> int:
    """เติมตัวเลขปลอมแบบคงที่ต่อรหัส — ใช้ตอน SAP ยังต่อไม่ได้ จะได้เห็นหน้าเว็บทำงานจริง

    สุ่มจากรหัสสินค้า (ไม่ใช่สุ่มสด) รันซ้ำกี่รอบก็ได้เลขเดิม เลขจะได้ไม่กระพริบไปมา
    ให้ ~15% เป็นของหมด จะได้เห็นทั้งการ์ดปกติและการ์ดทึบ
    """
    now = utcnow()
    for matnr in matnrs:
        seed = int(hashlib.md5(matnr.encode()).hexdigest()[:8], 16)
        bucket = seed % 100
        mto = False
        if bucket < 8:  # หมดสนิท ไม่มีรอบเข้า -> ถูกซ่อนจากหน้ารายการ
            ready, later = 0, 0
        elif bucket < 15:  # ของหมดแต่มีรอบเข้า -> พรีออเดอร์
            ready, later = 0, seed % 9 + 2
        elif bucket < 22:  # สินค้าสั่งทำ -> พรีออเดอร์เหมือนกัน แต่ไม่มีรอบเข้าให้บอก
            ready, later, mto = 0, 0, True
        else:
            ready, later = seed % 40 + 1, 0
        _write(db, matnr, ready=ready, later=later,
               later_date=(date.today() + timedelta(days=seed % 30 + 7)) if later else None,
               known=True, now=now, mto=mto)
        if on_batch:
            on_batch(1)
    db.commit()
    return len(matnrs)


def refresh(db: Session, matnrs: list[str], req_date: date | None = None,
            on_batch: Callable[[int], None] | None = None) -> int:
    """ยิง SAP เป็นชุดแล้วเขียนลง cache — คืนจำนวนรหัสที่อัปเดตสำเร็จ

    ชุดละ stock_batch_size รหัส เพราะรหัสเสียตัวเดียวทำให้ SAP ตอบว่างทั้งบิล
    (client จะถอยไปไล่ยิงทีละรายการให้เอง) ชุดเล็กจำกัดความเสียหายตรงนั้น
    SAP ล่มกลางทางก็หยุดแค่ชุดนั้น ชุดที่เขียนไปแล้วยังอยู่

    on_batch: เรียกทุกครั้งที่จบหนึ่งชุด พร้อมจำนวนรหัสในชุดนั้น — ให้สคริปต์เอาไปโชว์
    ความคืบหน้าได้ ตัวบริการเองไม่พิมพ์อะไรออกจอ (ถูกเรียกจาก request ด้วย)
    """
    s = get_settings()
    if not matnrs:
        return 0
    client = get_material_stock_client()
    when = req_date or req_date_for()
    now = utcnow()
    done = 0
    for i in range(0, len(matnrs), s.stock_batch_size):
        chunk = matnrs[i : i + s.stock_batch_size]
        try:
            got = client.check(chunk, when)
        except SapError as e:
            log.warning("refresh availability %d รหัสไม่สำเร็จ: %s", len(chunk), e)
            if on_batch:
                on_batch(len(chunk))
            continue
        # จับคู่ด้วยรหัส ไม่ใช่ตำแหน่ง — สินค้าชุดทำให้ SAP ตอบกลับมาเกินจำนวนที่ขอ
        for matnr in chunk:
            line = got.get(matnr)
            if line is None:  # SAP ไม่รู้จักรหัสนี้
                _write(db, matnr, ready=0, later=0, later_date=None, known=False, now=now, sites=[])
                continue
            _write(db, matnr, ready=line.available, later=line.committed, later_date=line.committed_date,
                   known=True, now=now, mto=line.made_to_order, sites=line.sites)
            done += 1
        db.commit()
        if on_batch:
            on_batch(len(chunk))
    return done


# รหัสที่กำลังยิง SAP อยู่ ณ ตอนนี้ — กันคน 50 คนเปิดหน้าเดียวกันพร้อมกันแล้วยิงซ้ำ 50 รอบ
_inflight: set[str] = set()
_inflight_lock = threading.Lock()


def refresh_stale_bg(matnrs: list[str]) -> None:
    """รีเฟรชตัวที่หมดอายุแบบเบื้องหลัง — เรียกจาก BackgroundTasks หลังส่ง response ไปแล้ว

    เปิด session ของตัวเองเพราะ session ของ request ปิดไปตั้งแต่ตอบ response แล้ว
    จำกัดรอบละ 1 ชุด (stock_batch_size) เพื่อไม่ให้คนเปิดหน้าเว็บคนเดียว
    ลาก SAP ไปทั้งแคตตาล็อก — ที่เหลือเป็นงานของ job รายชั่วโมง
    """
    from app.db.session import SessionLocal

    take = get_settings().stock_batch_size
    with SessionLocal() as db:
        todo = stale_matnrs(db, matnrs)[:take]
        with _inflight_lock:
            todo = [m for m in todo if m not in _inflight]
            _inflight.update(todo)
        if not todo:
            return
        try:
            refresh(db, todo)
        except Exception:  # งานเบื้องหลัง — พังแล้วต้องไม่กระทบ request ที่ตอบไปแล้ว
            log.exception("refresh availability เบื้องหลังไม่สำเร็จ")
        finally:
            with _inflight_lock:
                _inflight.difference_update(todo)
