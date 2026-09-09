"""rebuild sb_products จาก mdm_products บนฐานเว็บ (10.9.11.111)

    python -m app.etl.rebuild_products            # ปกติ — มีด่านกันทุกชั้น
    python -m app.etl.rebuild_products --dry-run  # ดูว่าจะได้กี่แถว ไม่แตะตารางจริง
    python -m app.etl.rebuild_products --force    # ข้ามด่าน (ใช้เมื่อรู้ตัวว่ากำลังทำอะไร)

ทำไมต้องมีด่าน: mdm_products เป็นของทีมอื่น และ job ของเขา TRUNCATE แล้ว INSERT ใหม่
ทั้งตาราง (~200k แถว ใช้เวลาหลายนาที) ถ้าเราบังเอิญอ่านระหว่างนั้น จะได้สินค้าไม่ครบ
แล้วเอาไปทับของดีที่มีอยู่ — เว็บสินค้าหายครึ่งหนึ่งโดยไม่มีใครรู้
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from app.core.config import get_settings

# console ไทยบน Windows เป็น cp874 พิมพ์ → หรืออิโมจิไม่ได้ — บังคับ UTF-8 ไว้ก่อน
for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "encoding", "") and _s.encoding.lower() not in ("utf-8", "utf8"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SQL_DIR = Path(__file__).resolve().parents[2] / "sql" / "sbweb"
REBUILD_SQL = SQL_DIR / "011_rebuild_sb_products_v3.sql"

# ต้นทางต้องนิ่ง: นับสองครั้งห่างกันเท่านี้แล้วต้องได้เลขเดิม
STABLE_WAIT_SECONDS = 10
STABLE_MAX_TRIES = 30          # รอสูงสุด ~5 นาที เผื่อ job ต้นทางยังโหลดอยู่
# ของใหม่ห้ามน้อยกว่าของเดิมเกินเท่านี้ ไม่งั้นถือว่าผิดปกติ
MAX_SHRINK_RATIO = 0.20


def _split_statements(sql: str) -> list[str]:
    """แยก .sql เป็นทีละ statement (pymysql ส่งทีเดียวหลาย statement ไม่ได้)"""
    import re

    lines = [
        re.sub(r"\s--\s.*$", "", ln)
        for ln in sql.splitlines()
        if not ln.strip().startswith("--")
    ]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def _count(conn: Connection, table: str, where: str = "") -> int:
    return conn.execute(text(f"SELECT COUNT(*) FROM {table} {where}")).scalar() or 0


def wait_until_source_stable(conn: Connection) -> int:
    """รอจน mdm_products หยุดเปลี่ยน แล้วคืนจำนวนแถว — ถ้าไม่นิ่งจนหมดเวลาให้ raise"""
    prev = _count(conn, "mdm_products")
    for attempt in range(STABLE_MAX_TRIES):
        time.sleep(STABLE_WAIT_SECONDS)
        now = _count(conn, "mdm_products")
        if now == prev:
            print(f"  ต้นทางนิ่งแล้ว: {now:,} แถว")
            return now
        print(f"  ต้นทางยังโหลดอยู่ {prev:,} → {now:,} (รอบ {attempt + 1}) รอต่อ...")
        prev = now
    raise RuntimeError(
        f"mdm_products ยังเปลี่ยนอยู่หลังรอ {STABLE_MAX_TRIES * STABLE_WAIT_SECONDS}s — "
        "job ต้นทางน่าจะยังไม่จบ ลองใหม่ทีหลัง"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="rebuild sb_products จาก mdm_products")
    ap.add_argument("--dry-run", action="store_true", help="นับอย่างเดียว ไม่เขียนอะไร")
    ap.add_argument("--force", action="store_true", help="ข้ามด่านเช็คความนิ่ง/จำนวนแถว")
    args = ap.parse_args()

    url = get_settings().sbweb_database_url
    if not url:
        print("! ไม่ได้ตั้ง SBWEB_DATABASE_URL ใน .env", file=sys.stderr)
        return 2

    batch_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    started = datetime.now()
    # AUTOCOMMIT สำคัญ: ถ้าอยู่ใน transaction เดียว InnoDB REPEATABLE READ จะค้าง snapshot
    # นับกี่ครั้งก็ได้เลขเดิม → มองไม่เห็นว่าต้นทางกำลังโหลดอยู่
    engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600, isolation_level="AUTOCOMMIT")

    with engine.connect() as conn:
        print(f"batch {batch_id}")

        if args.force:
            src_rows = _count(conn, "mdm_products")
            print(f"  --force: ข้ามด่าน · ต้นทาง {src_rows:,} แถว")
        else:
            src_rows = wait_until_source_stable(conn)

        # v2 เก็บทุกแถวที่มีรหัส+ชื่อ แล้วค่อยใช้ธง is_public ตัดสินว่าลูกค้าเห็นตัวไหน
        # (ของเดิมกรอง NETPRICE/PATH ตั้งแต่ตรงนี้ ทำให้เซลล์ค้นสินค้าบางตัวไม่เจอเลย)
        eligible = _count(
            conn,
            "mdm_products",
            "WHERE MATNR IS NOT NULL AND TRIM(MATNR)<>'' "
            "AND MAKTX IS NOT NULL AND TRIM(MAKTX)<>''",
        )
        current = _count(conn, "sb_products")
        print(f"  ต้นทาง {src_rows:,} · จะเก็บ {eligible:,} · ของเดิม {current:,}")

        if args.dry_run:
            # ประมาณคร่าวๆ ว่าจะเหลือกี่ตัวให้ลูกค้าเห็น — เช็คก่อนรันจริงว่าเกณฑ์ไม่เพี้ยน
            for label, where in (
                ("ยังขายอยู่ (active)", ""),
                ("มีชื่อจากเว็บจริง", "AND a.MATNR IN (SELECT sku FROM sb_products_image)"),
            ):
                n = conn.execute(
                    text(f"SELECT COUNT(*) FROM mdm_products_active a WHERE 1=1 {where}")
                ).scalar()
                print(f"    {label}: {n:,}")
            print("  --dry-run: จบแค่นี้ ไม่เขียนอะไร")
            return 0

        # ของใหม่หดผิดปกติ = อย่าเพิ่งทับ ของเดิมที่ยังดีอยู่มีค่ากว่าของใหม่ที่น่าสงสัย
        if current and not args.force:
            shrink = (current - eligible) / current
            if shrink > MAX_SHRINK_RATIO:
                msg = (
                    f"ของใหม่ {eligible:,} น้อยกว่าของเดิม {current:,} ถึง {shrink:.0%} "
                    f"(เกินเพดาน {MAX_SHRINK_RATIO:.0%}) — ไม่สลับตาราง เก็บของเดิมไว้"
                )
                print(f"  ! {msg}")
                _log(conn, batch_id, started, "skipped", src_rows, 0, eligible, msg)
                return 1

        _log(conn, batch_id, started, "running", src_rows, 0, 0, None)

        sql = REBUILD_SQL.read_text(encoding="utf-8").replace(":BATCH", batch_id)
        inserted = 0
        # cursor ดิบ — exec_driver_sql ส่ง params ว่างไปให้ pymysql แล้วมันไปตีความ %
        # ใน CONCAT('%', sku, '%') เป็น format specifier แล้วพัง
        cur = conn.connection.cursor()
        try:
            for stmt in _split_statements(sql):
                t0 = time.time()
                cur.execute(stmt)
                if stmt.lstrip().upper().startswith("INSERT INTO SB_PRODUCTS_NEW"):
                    inserted = cur.rowcount or 0
                    print(f"  insert {inserted:,} แถว ({time.time() - t0:.0f}s)")
        except Exception as exc:  # noqa: BLE001 — อยากได้ทุกเหตุลง log
            _log(conn, batch_id, started, "failed", src_rows, 0, 0, str(exc)[:1000])
            print(f"  ! ล้มเหลว: {exc}", file=sys.stderr)
            # ตารางจริงยังไม่ถูกแตะ (สลับเป็น step สุดท้าย) — เว็บยังใช้ของเดิมได้
            conn.exec_driver_sql("DROP TABLE IF EXISTS sb_products_new")
            return 1

        final = _count(conn, "sb_products")
        _log(conn, batch_id, started, "ok", src_rows, final, src_rows - inserted, None)
        print(f"  เสร็จ: sb_products = {final:,} แถว")
    return 0


def _log(
    conn: Connection,
    batch_id: str,
    started: datetime,
    status: str,
    rows_in: int,
    rows_out: int,
    rows_skipped: int,
    message: str | None,
) -> None:
    conn.execute(
        text(
            "INSERT INTO sb_import_log "
            "(batch_id, stage, started_at, finished_at, status, rows_in, rows_out, rows_skipped, message) "
            "VALUES (:b, 'rebuild', :s, :f, :st, :ri, :ro, :rs, :m)"
        ),
        {
            "b": batch_id,
            "s": started,
            "f": None if status == "running" else datetime.now(),
            "st": status,
            "ri": rows_in,
            "ro": rows_out,
            "rs": max(rows_skipped, 0),
            "m": message,
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())
