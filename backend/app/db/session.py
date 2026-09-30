from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _make_engine(url: str):
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")  # SQLite ต้องเปิด foreign key เอง
            # WAL: คนอ่านไม่ถูกล็อกตอนมีคนเขียน และเห็นข้อมูลชุดเดิมจนกว่าการเขียนจะ commit เสร็จ
            #
            # โหมดเดิม (delete) ตอน ETL เขียนทับสินค้า 25,000 แถว หน้าเว็บที่ลูกค้าเปิดค้างอยู่
            # จะโดนล็อกจนหมดเวลารอแล้วพัง — ซึ่งเกิดทุกครั้งที่รัน sync_all
            #
            # ค่านี้ติดอยู่กับไฟล์ฐานอยู่แล้ว ตั้งซ้ำตรงนี้เผื่อฐานใหม่ (เครื่อง dev คนอื่น / เทส)
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            # ถ้ายังชนกันจริงๆ ให้รอถึง 30 วิแทนที่จะพังทันที (ETL เขียนเป็นก้อนใหญ่)
            dbapi_conn.execute("PRAGMA busy_timeout=30000")

        return engine
    if url.startswith("mysql"):
        # MySQL/MariaDB ตัด connection ที่ idle เกิน wait_timeout (ปกติ 8 ชม.) → รีไซเคิลก่อนถึงเวลา
        return create_engine(url, pool_pre_ping=True, pool_recycle=3600)
    return create_engine(url, pool_pre_ping=True)


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
