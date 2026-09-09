from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _make_engine(url: str):
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # SQLite ต้องเปิด foreign key เอง
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

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
