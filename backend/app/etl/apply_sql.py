"""รันไฟล์ .sql ใน backend/sql/sbweb กับฐานเว็บ (10.9.11.111) ทีละ statement

    python -m app.etl.apply_sql 008_sb_products_v2.sql --dry-run   # ดูว่าจะรันอะไรบ้าง
    python -m app.etl.apply_sql 008_sb_products_v2.sql

ไฟล์พวกนี้ยุ่งกับตาราง sb_* ของเราเท่านั้น สคริปต์เลยกันไว้ชั้นหนึ่ง:
ถ้าเจอ DROP/ALTER/TRUNCATE ที่ชี้ไปตารางไม่ได้ขึ้นต้นด้วย sb_ จะไม่ยอมรัน
(ฐานนี้เป็นฐานเว็บจริง มี 222 ตารางของระบบเดิมอยู่ด้วย)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from sqlalchemy import create_engine

from app.core.config import get_settings
from app.etl.rebuild_products import _split_statements

for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "encoding", "") and _s.encoding.lower() not in ("utf-8", "utf8"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SQL_DIR = Path(__file__).resolve().parents[2] / "sql" / "sbweb"
DESTRUCTIVE = re.compile(r"^\s*(DROP|ALTER|TRUNCATE|RENAME)\s+(TABLE|VIEW)?\s*(IF\s+EXISTS\s+)?`?([A-Za-z0-9_]+)`?", re.I)


def guard(stmt: str) -> None:
    m = DESTRUCTIVE.match(stmt)
    if m and not m.group(4).lower().startswith("sb_"):
        raise SystemExit(f"! ปฏิเสธ: statement นี้ไปยุ่งตารางที่ไม่ใช่ sb_* → {stmt[:120]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="รันไฟล์ sql กับฐานเว็บ")
    ap.add_argument("filename", help="ชื่อไฟล์ใน backend/sql/sbweb")
    ap.add_argument("--dry-run", action="store_true", help="โชว์ statement เฉยๆ ไม่รัน")
    args = ap.parse_args()

    path = SQL_DIR / args.filename
    if not path.exists():
        raise SystemExit(f"! ไม่พบไฟล์ {path}")
    url = get_settings().sbweb_database_url
    if not url:
        raise SystemExit("! ไม่ได้ตั้ง SBWEB_DATABASE_URL ใน .env")

    stmts = _split_statements(path.read_text(encoding="utf-8"))
    for s in stmts:
        guard(s)
    print(f"{path.name}: {len(stmts)} statement")

    if args.dry_run:
        for s in stmts:
            print("  ---", " ".join(s.split())[:110])
        return 0

    engine = create_engine(url, pool_pre_ping=True, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        cur = conn.connection.cursor()  # cursor ดิบ — เลี่ยงปัญหา % ใน SQL ถูกตีความเป็น param
        for i, s in enumerate(stmts, 1):
            cur.execute(s)
            print(f"  [{i}/{len(stmts)}] ok · {' '.join(s.split())[:90]}")
    print("เสร็จ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
