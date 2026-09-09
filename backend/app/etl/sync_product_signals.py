"""สัญญาณ "มาใหม่" / "ขายดี" จาก Magento (10.9.12.67) -> sb_product_signals -> materials

    python -m app.etl.sync_product_signals              # ยอดขายย้อนหลัง 365 วัน
    python -m app.etl.sync_product_signals --days 90
    python -m app.etl.sync_product_signals --dry        # ดูผลอย่างเดียว ไม่เขียนอะไร

ทำไมต้องดึงจาก Magento: ฐานแอปมี is_new แค่ 4 ตัว (มาจาก seed) และตาราง best_sellers
ของเราคำนวณจาก user_events ของระบบใหม่ซึ่งยังไม่มีทราฟฟิกจริง — สองแถวบนหน้าค้นหาเลย
ว่างเปล่า ในขณะที่เว็บจริงมีทั้งวันที่สินค้าขึ้นเว็บและออเดอร์ย้อนหลัง 5 ปีอยู่แล้ว

    created_at   catalog_product_entity.created_at
    sold_qty     SUM(sales_order_item.qty_ordered) ในช่วง N วัน (ไม่นับที่ยกเลิก)
    sold_orders  จำนวนออเดอร์ที่มีสินค้าตัวนี้

sku ฝั่ง Magento = matnr ฝั่งเรา ตรงกันทั้งชุด จึง join ตรงๆ ได้
เดินทางเดียวกับ ETL ตัวอื่น: Magento -> ตาราง sb_* บนฐานเว็บ -> import เข้าฐานแอป
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.catalog import Material

for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "encoding", "") and _s.encoding.lower() not in ("utf-8", "utf8"):
        _s.reconfigure(encoding="utf-8", errors="replace")

CHUNK = 2000

# ออเดอร์ที่ยกเลิก/ปิดคืนของ ไม่ควรนับเป็นยอดขาย และ qty_canceled/refunded หักออกด้วย
SALES_SQL = """
SELECT i.sku,
       SUM(GREATEST(i.qty_ordered - i.qty_canceled - i.qty_refunded, 0)) AS qty,
       COUNT(DISTINCT i.order_id)                                        AS orders
  FROM sales_order_item i
  JOIN sales_order o ON o.entity_id = i.order_id
 WHERE i.created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
   AND o.status NOT IN ('canceled', 'closed')
   AND i.parent_item_id IS NULL
 GROUP BY i.sku
"""


def _magento():
    url = get_settings().magento_url
    if not url:
        raise SystemExit("! ไม่ได้ตั้ง MAGENTO_HOST/USER/PASSWORD ใน .env (ฐาน Magento บน 10.9.12.67)")
    return create_engine(url, pool_pre_ping=True)


def fetch(days: int) -> dict[str, dict]:
    """รวมสองคิวรีเป็นแถวเดียวต่อ matnr — ตัวที่ยังไม่เคยขายก็ยังมีแถว (sold_qty = 0)"""
    out: dict[str, dict] = {}
    with _magento().connect() as c:
        cur = c.connection.cursor()
        cur.execute("SELECT sku, created_at FROM catalog_product_entity")
        for sku, created in cur.fetchall():
            out[str(sku)] = {"created_at": created, "sold_qty": 0, "sold_orders": 0}
        cur.execute(SALES_SQL, (days,))
        for sku, qty, orders in cur.fetchall():
            row = out.setdefault(str(sku), {"created_at": None, "sold_qty": 0, "sold_orders": 0})
            row["sold_qty"] = int(qty or 0)
            row["sold_orders"] = int(orders or 0)
    return out


UPSERT_SQL = """
INSERT INTO sb_product_signals (matnr, created_at, sold_qty, sold_orders, window_days)
VALUES (%s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
  created_at  = VALUES(created_at),
  sold_qty    = VALUES(sold_qty),
  sold_orders = VALUES(sold_orders),
  window_days = VALUES(window_days)
"""


def upsert_sbweb(rows: dict[str, dict], days: int) -> None:
    eng = create_engine(get_settings().sbweb_database_url, pool_pre_ping=True)
    data = [(m, r["created_at"], r["sold_qty"], r["sold_orders"], days) for m, r in rows.items()]
    with eng.connect() as c:
        raw = c.connection
        cur = raw.cursor()
        for i in range(0, len(data), CHUNK):
            cur.executemany(UPSERT_SQL, data[i : i + CHUNK])
        raw.commit()
    print(f"  sb_product_signals: upsert {len(data):,} แถว")


def import_app(db: Session, rows: dict[str, dict]) -> int:
    """เขียนทับเฉพาะสินค้าที่มีอยู่ในฐานแอป — Magento มีของมากกว่า (รวมที่ไม่ได้ขายผ่าน SAP)"""
    n = 0
    for i, matnr in enumerate(db.scalars(select(Material.matnr)).all()):
        got = rows.get(matnr)
        if not got:
            continue
        m = db.get(Material, matnr)
        m.created_at = got["created_at"]
        m.sold_qty = got["sold_qty"]
        n += 1
        if i % CHUNK == 0:
            db.flush()
    db.commit()
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="ดึงวันที่ขึ้นเว็บ + ยอดขายจริงจาก Magento")
    ap.add_argument("--days", type=int, default=365, help="ช่วงที่นับยอดขาย (ค่าเริ่มต้น 365 วัน)")
    ap.add_argument("--dry", action="store_true", help="แสดงผลอย่างเดียว ไม่เขียนอะไร")
    ap.add_argument("--no-sbweb", action="store_true", help="ข้ามการเขียนฐานเว็บ ลงเฉพาะฐานแอป")
    args = ap.parse_args()

    rows = fetch(args.days)
    sold = {m: r for m, r in rows.items() if r["sold_qty"] > 0}
    print(f"Magento: สินค้า {len(rows):,} · มียอดขายใน {args.days} วัน {len(sold):,}")
    for m, r in sorted(sold.items(), key=lambda kv: -kv[1]["sold_qty"])[:5]:
        print(f"    {m} · ขาย {r['sold_qty']} ชิ้น / {r['sold_orders']} ออเดอร์")
    if args.dry:
        print("(--dry ไม่เขียนอะไร)")
        return 0

    if not args.no_sbweb:
        upsert_sbweb(rows, args.days)
    with SessionLocal() as db:
        n = import_app(db, rows)
        have_new = db.scalar(select(func.count()).select_from(Material).where(Material.created_at.isnot(None)))
        have_sold = db.scalar(select(func.count()).select_from(Material).where(Material.sold_qty > 0))
        print(f"  materials: อัปเดต {n:,} แถว · มีวันที่ {have_new:,} · มียอดขาย {have_sold:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
