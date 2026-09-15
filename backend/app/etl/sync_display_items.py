"""สร้าง/อัปเดต "สินค้าตัวโชว์" — แปลงรหัส 19 เป็น 20 แล้วถามสต็อกจาก ZAIBAPI_MATERIAL_STOCK

    .venv\\Scripts\\python.exe -m app.etl.sync_display_items              # เฉพาะตัวที่หมดอายุ (TTL 1 ชม.)
    .venv\\Scripts\\python.exe -m app.etl.sync_display_items --all        # ถาม SAP ใหม่ทุกตัว
    .venv\\Scripts\\python.exe -m app.etl.sync_display_items --limit 100
    .venv\\Scripts\\python.exe -m app.etl.sync_display_items --mock       # ไม่ยิง SAP จริง

กติกา (ตามที่ตกลงไว้):
  รหัสขายปกติ 19xxxxxx  ->  ตัวโชว์ 20xxxxxx (เลขท้ายเหมือนกันทุกตัว)
  ถาม ZAIBAPI_MATERIAL_STOCK ด้วยรหัส 20 · มีของ = โชว์บนเว็บ · ไม่มีของ = ซ่อน
  รันทุก 1 ชม. เท่ากับ refresh_stock (TTL เดียวกัน = stock_cache_ttl_minutes)

ทำไมต้องปั้นแถวสินค้าขึ้นมาเอง:
  รหัส 20 ไม่มีอยู่ในฐานเว็บ (sb_products) เลยสักตัว — เช็คแล้ว 0 แถวจาก 199,000 แถว
  มันมีอยู่แค่ใน SAP ในฐานะ "ของที่ตั้งโชว์หน้าร้าน" ซึ่งตอบมาแต่จำนวน ไม่มีชื่อ/รูป/ราคา
  ชื่อ รูป ราคา หมวด จึงต้องก๊อปจากตัวปกติ (19) ที่เป็นสินค้ารุ่นเดียวกัน

  ผลที่ตามมาที่ต้องรู้: ราคาตัวโชว์จะเท่าตัวปกติ เพราะไม่มีที่ไหนบอกราคาลดของตัวโชว์
  ถ้าวันหลังมีราคาตัวโชว์จริง ให้แก้ที่ _clone_prices() ที่เดียว

ตัวเลขจากการยิงจริง (สุ่ม 120 รหัส): SAP รู้จัก 97% · มีของ 71% · จำนวนกลาง 5 ชิ้น
ทดสอบรหัสมั่ว (20999999, 29027037) แล้ว SAP ตอบ "ไม่มีแถว" ไม่ได้มั่วตัวเลขให้
"""
from __future__ import annotations

import argparse
import sys
import time

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import SessionLocal
from app.models.catalog import Material, MaterialPrice, ProductStock
from app.models.common import utcnow
from app.services import product_stock_service
from app.services.catalog_service import matnr_groups

for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "encoding", "") and _s.encoding.lower() not in ("utf-8", "utf8"):
        _s.reconfigure(encoding="utf-8", errors="replace")

# ฟิลด์ที่ตัวโชว์ใช้ร่วมกับตัวปกติได้ — เป็นของรุ่นเดียวกัน หน้าตาเดียวกัน กล่องเท่ากัน
# ที่ไม่ก๊อปมาโดยตั้งใจ: is_new / is_bestseller / sold_qty / created_at / abc_class
# เพราะเป็นสัญญาณการขายของ "ตัวปกติ" ถ้าก๊อปมาตัวโชว์จะไปแย่งอันดับในหน้า "มาใหม่/ขายดี"
DISPLAY_LABEL = "สินค้าตัวโชว์"

CLONE_FIELDS = (
    "name_th", "name_en", "name_raw", "variant", "spec", "description",
    "category_id", "brand_id", "room", "color", "style", "image_url",
    "requires_install", "is_takeaway_ok", "volume_m3", "weight_kg", "tags",
)


def display_matnr(matnr: str) -> str:
    """19xxxxxx -> 20xxxxxx (เลขท้ายเหมือนเดิม)"""
    groups = matnr_groups()
    src, dst = groups.get("regular", "19"), groups.get("display", "20")
    return dst + matnr[len(src):]


def _clone_prices(db: Session, parent: Material, code: str) -> None:
    """ราคาตัวโชว์ = ราคาตัวปกติ · ยังไม่มีแหล่งไหนบอกราคาลดของตัวโชว์ (ดูหัวไฟล์)"""
    db.execute(MaterialPrice.__table__.delete().where(MaterialPrice.matnr == code))
    for p in parent.prices:
        db.add(MaterialPrice(matnr=code, tier=p.tier, price=p.price, valid_from=p.valid_from, valid_to=p.valid_to))


def _upsert(db: Session, parent: Material, code: str, in_stock: bool) -> None:
    row = db.get(Material, code)
    fields = {k: getattr(parent, k) for k in CLONE_FIELDS}
    # is_public คือธงเดียวที่ทุกหน้าใช้กรองอยู่แล้ว — ของหมดก็แค่ปิดธง ไม่ต้องลบแถวทิ้ง
    # เก็บแถวไว้เพราะรอบหน้าของอาจกลับมา แล้วจะได้ไม่ต้องปั้นใหม่ทั้งชุด
    # ต่อท้ายชื่อไปเลย ไม่ใช่โชว์แค่ป้ายบนการ์ด — ชื่อเป็นตัวเดียวที่ติดไปทุกที่
    # ทั้งตะกร้า ใบเสนอราคา ใบสั่งซื้อ และ MCP ลูกค้าจะได้ไม่มีทางเข้าใจผิดว่าซื้อของใหม่
    # ก๊อปชื่อจากตัวปกติใหม่ทุกรอบแล้วค่อยต่อท้าย จึงไม่มีทางต่อซ้อนกันหลายรอบ
    fields["name_th"] = f"{parent.name_th} ({DISPLAY_LABEL})"
    fields.update(sku=code, is_public=in_stock, is_new=False, is_bestseller=False, sold_qty=0, synced_at=utcnow())
    if row:
        for k, v in fields.items():
            setattr(row, k, v)
    else:
        db.add(Material(matnr=code, **fields))
    _clone_prices(db, parent, code)


def sync(db: Session, *, refresh_all: bool, limit: int | None, mock: bool) -> tuple[int, int, int]:
    """คืน (ถาม SAP กี่รหัส, โชว์กี่ตัว, ซ่อนกี่ตัว)"""
    src_prefix = matnr_groups().get("regular", "19")
    # โหลดราคามาพร้อมกันทีเดียว (selectinload) ไม่งั้นตอนก๊อปราคาจะยิง query ทีละตัว 3,000 กว่ารอบ
    parents = list(db.scalars(
        select(Material).options(selectinload(Material.prices))
        .where(Material.is_public.is_(True), Material.matnr.like(f"{src_prefix}%")).order_by(Material.matnr)
    ))
    if limit:
        parents = parents[:limit]
    by_code = {display_matnr(p.matnr): p for p in parents}
    codes = list(by_code)
    print(f"สินค้าขายปกติบนเว็บ {len(parents):,} ตัว -> ตัวโชว์ {len(codes):,} รหัส")

    todo = codes if refresh_all else product_stock_service.stale_matnrs(db, codes)
    if todo:
        print(f"  ถามสต็อก SAP {len(todo):,} รหัส" + (" (mock)" if mock else "") + " ...")
        t0 = time.monotonic()
        if mock:
            product_stock_service.refresh_mock(db, todo)
        else:
            product_stock_service.refresh(db, todo)
        print(f"  ถามเสร็จใน {time.monotonic() - t0:,.0f} วินาที")
    else:
        print("  สต็อกยังไม่หมดอายุ ไม่ต้องถาม SAP")

    # ตัดสินว่าโชว์/ซ่อนจาก cache เสมอ ไม่ใช่จากผลที่เพิ่งยิง — ตัวที่ไม่ได้อยู่ในรอบนี้
    # (ยังไม่หมดอายุ) ก็ต้องถูกตัดสินด้วย ไม่งั้นของที่หมดไปแล้วจะค้างโชว์อยู่
    stock = {r.matnr: r for r in db.scalars(select(ProductStock).where(ProductStock.matnr.in_(codes))).all()}
    shown = hidden = 0
    for code, parent in by_code.items():
        r = stock.get(code)
        # "มีของ" ของตัวโชว์ = มีของจริงอยู่ตอนนี้เท่านั้น
        # ไม่นับรอบที่จะเข้า (committed) และไม่นับสินค้าสั่งทำ เพราะตัวโชว์คือของที่ตั้งอยู่หน้าร้านจริง
        in_stock = bool(r and r.sap_known and r.ready_qty > 0)
        _upsert(db, parent, code, in_stock)
        shown += in_stock
        hidden += not in_stock
    db.commit()
    return len(todo), shown, hidden


def main() -> int:
    ap = argparse.ArgumentParser(description="สร้าง/อัปเดตสินค้าตัวโชว์ (MATNR 20) จากสต็อก SAP")
    ap.add_argument("--all", action="store_true", help="ถาม SAP ใหม่ทุกตัว ไม่สนว่ายังไม่หมดอายุ")
    ap.add_argument("--limit", type=int, default=None, help="จำกัดจำนวนสินค้าต้นทางต่อรอบ")
    ap.add_argument("--mock", action="store_true", help="ใส่ตัวเลขปลอมแทนการยิง SAP")
    args = ap.parse_args()

    with SessionLocal() as db:
        asked, shown, hidden = sync(db, refresh_all=args.all, limit=args.limit, mock=args.mock)
    print(f"เสร็จ: ถาม SAP {asked:,} รหัส · โชว์บนเว็บ {shown:,} ตัว · ซ่อน (ไม่มีของ) {hidden:,} ตัว")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
