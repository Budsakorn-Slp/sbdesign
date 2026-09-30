"""ยกหน้าเนื้อหาคงที่จาก CMS ของเว็บจริงมาไว้ในแอป — วิธีสั่งซื้อ / การรับประกัน / นโยบาย ฯลฯ

    .venv\\Scripts\\python.exe -m app.etl.sync_cms_pages
    .venv\\Scripts\\python.exe -m app.etl.sync_cms_pages --dry-run

ทำไมไม่เขียนเนื้อหาเอง: หน้าพวกนี้เป็นข้อความเชิงนโยบาย/กฎหมาย (นโยบายคืนสินค้า
ประกาศความเป็นส่วนตัว เงื่อนไขโปรโมชั่น) ที่ต้องตรงกับที่บริษัทประกาศไว้จริงคำต่อคำ
ถ้าเขียนใหม่เองแล้วเพี้ยนไปนิดเดียวก็กลายเป็นข้อมูลผิดที่ผูกพันบริษัท

อ่านจากตาราง cms_page ของ Magento โดยตรง (อ่านอย่างเดียว ห้ามเขียนกลับ)
บาง slug มีหลายแถว (คนละร้าน/คนละภาษา) — เลือกแถวภาษาไทยที่เนื้อหายาวสุด
เพราะเวอร์ชันไทยคือที่ลูกค้าเห็นจริง และตัวที่ยาวกว่ามักเป็นตัวที่อัปเดตล่าสุด
"""
from __future__ import annotations

import argparse
import re
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.etl.html_clean import clean
from app.db.session import SessionLocal
from app.models.content import InfoPage

for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "encoding", "") and _s.encoding.lower() not in ("utf-8", "utf8"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SITE = "https://www.sbdesignsquare.com/"

# slug -> ชื่อที่จะโชว์บนหน้าเรา (บาง title ใน CMS เป็น slug ดิบอย่าง "warranty"
# หรือเป็นภาษาอังกฤษ ทั้งที่เนื้อหาข้างในเป็นไทย — ตั้งชื่อไทยกำกับไว้เองให้อ่านรู้เรื่อง)
PAGES = {
    "shopping-guide": "วิธีการสั่งซื้อสินค้า",
    "warranty": "การรับประกันสินค้า",
    "return-policy": "การเปลี่ยนเคลม/ยกเลิกสินค้า",
    "care-instruction": "การดูแลรักษาสินค้า",
    "shipping-policy": "การจัดส่งสินค้า",
    "online-promotion-condition": "เงื่อนไขโปรโมชั่น Online",
    "privacy-notice": "ประกาศความเป็นส่วนตัว",
    "privacy-policy": "นโยบายความเป็นส่วนตัว",
    "sb-furniture-group": "SB FURNITURE GROUP",
    "doing-business": "ร่วมธุรกิจกับเรา",
    "career": "ร่วมงานกับเรา",
    "design-service": "Design Service",
    "pro-service": "Pro Service",
}

def fetch(c, slug: str) -> dict | None:
    rows = c.execute(text("""
        SELECT title, content FROM cms_page
        WHERE identifier = :s AND is_active = 1 AND content IS NOT NULL
    """), {"s": slug}).all()
    if not rows:
        return None
    # ไทยก่อน แล้วค่อยยาวสุด — ดูจากว่ามีอักษรไทยในเนื้อหาไหม
    def score(r):
        return (1 if re.search(r"[฀-๿]", r[1] or "") else 0, len(r[1] or ""))
    title, content = max(rows, key=score)
    return {"title": title, "content": content}


def sync(db: Session, *, dry_run: bool) -> list[tuple[str, str, int]]:
    s = get_settings()
    if not s.magento_url:
        raise SystemExit("! ยังไม่ได้ตั้งค่าเชื่อม Magento ใน .env")
    eng = create_engine(s.magento_url, pool_pre_ping=True)
    out: list[tuple[str, str, int]] = []
    with eng.connect() as c:
        for slug, title_th in PAGES.items():
            got = fetch(c, slug)
            if not got:
                out.append((slug, "ไม่เจอใน CMS", 0))
                continue
            body = clean(got["content"], SITE)
            out.append((slug, title_th, len(body)))
            if dry_run:
                continue
            row = db.get(InfoPage, slug)
            if not row:
                row = InfoPage(slug=slug)
                db.add(row)
            row.title = title_th
            row.body_html = body
            row.source_url = SITE + slug
    eng.dispose()
    if not dry_run:
        db.commit()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="ยกหน้าเนื้อหาคงที่จาก CMS ของเว็บจริง")
    ap.add_argument("--dry-run", action="store_true", help="ดูผลก่อน ไม่เขียนลงฐาน")
    args = ap.parse_args()
    with SessionLocal() as db:
        rows = sync(db, dry_run=args.dry_run)
    ok = [r for r in rows if r[2]]
    for slug, title, n in rows:
        print(f"  {slug:<28} {title:<28} {n:>7,} ตัวอักษร" if n else f"  {slug:<28} {title}")
    print(f"เสร็จ: {len(ok)}/{len(rows)} หน้า" + (" (dry-run ไม่ได้เขียน)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
