"""เช็คว่าเชื่อมต่อฐานข้อมูลติดไหม

    python -m app.dbcheck                 # ใช้ DATABASE_URL จาก env / backend/.env
    python -m app.dbcheck --url postgresql+psycopg://sb:sb_secret@localhost:5432/sbdesign

exit code 0 = ต่อได้ · 1 = ต่อไม่ได้ (พิมพ์สาเหตุให้)
"""
import argparse
import sys
import time

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings


def masked(url: str) -> str:
    try:
        u = make_url(url)
        return u.render_as_string(hide_password=True)
    except Exception:
        return url


def check(url: str, timeout: float = 5.0) -> bool:
    print(f"DATABASE_URL = {masked(url)}")
    kwargs = {}
    if url.startswith("postgresql"):
        kwargs["connect_args"] = {"connect_timeout": int(timeout)}
    elif url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    t0 = time.perf_counter()
    try:
        engine = create_engine(url, **kwargs)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            ms = (time.perf_counter() - t0) * 1000
            if engine.dialect.name == "postgresql":
                ver = conn.execute(text("SELECT version()")).scalar()
                dbname = conn.execute(text("SELECT current_database()")).scalar()
                print(f"OK  postgresql · db={dbname} · {ms:.0f} ms")
                print(f"    {str(ver).split(',')[0]}")
            else:
                ver = conn.execute(text("SELECT sqlite_version()")).scalar()
                print(f"OK  sqlite {ver} · {ms:.0f} ms")
            tables = inspect(conn).get_table_names()
            print(f"    tables: {len(tables)}" + (f" ({', '.join(sorted(tables)[:12])}{'…' if len(tables) > 12 else ''})" if tables else " (ยังไม่ได้รัน alembic upgrade head)"))
            if "alembic_version" in tables:
                rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                print(f"    alembic revision: {rev}")
        engine.dispose()
        return True
    except Exception as e:  # noqa: BLE001
        ms = (time.perf_counter() - t0) * 1000
        print(f"FAIL ต่อไม่ได้ ({ms:.0f} ms): {type(e).__name__}: {str(e).strip().splitlines()[0]}")
        if url.startswith("postgresql"):
            print("    เช็ค: Postgres รันอยู่ไหม (docker compose up db) · host/port/user/password ใน .env ถูกไหม · firewall")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="เช็คการเชื่อมต่อ DB")
    ap.add_argument("--url", default=None, help="override DATABASE_URL")
    ap.add_argument("--timeout", type=float, default=5.0)
    args = ap.parse_args()
    url = args.url or get_settings().database_url
    return 0 if check(url, args.timeout) else 1


if __name__ == "__main__":
    sys.exit(main())
