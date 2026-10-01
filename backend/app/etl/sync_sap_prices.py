"""ดึงราคาสินค้าจาก SAP มาเก็บเป็น snapshot JSON แล้วอัปเดตราคาในฐาน — งานรายวัน

    python -m app.etl.sync_sap_prices --dry-run     # ดูว่าจะเปลี่ยนอะไรบ้าง ไม่เขียนฐาน
    python -m app.etl.sync_sap_prices               # เขียนจริง
    python -m app.etl.sync_sap_prices --from-file   # ใช้ snapshot ที่ดึงไว้แล้ว ไม่ยิง SAP

ทำไมต้องมี snapshot JSON ไม่ใช่ยิงเข้าฐานตรงๆ:
  1. ยิง SAP รอบหนึ่งใช้เวลาหลายนาที ถ้าเขียนฐานพังกลางทางต้องเริ่มใหม่ทั้งหมด
     มี snapshot แล้ว --from-file ทำซ้ำได้ในไม่กี่วินาที โดยไม่กวน SAP อีกรอบ
  2. เก็บบรรทัดเงื่อนไขดิบไว้ด้วย พอทีมสรุปสูตรราคาสมาชิกได้ ก็คำนวณจากไฟล์เดิมได้เลย
  3. เทียบย้อนหลังได้ว่าราคาเปลี่ยนเมื่อไร เพราะเก็บไฟล์ย้อนหลังไว้ 14 วัน

ขอบเขต — แตะอะไรและไม่แตะอะไร:
  * 19xxx (สินค้าปกติ) เก็บลง snapshot ไว้อ้างอิงเท่านั้น **ไม่เขียนทับฐาน**
    ราคาขายของกลุ่มนี้มาจาก sb_products ซึ่งคิดส่วนลดมาเรียบร้อยแล้ว
  * 20xxx (ตัวโชว์) คือของที่งานนี้แก้จริง — เดิมก๊อปราคา "หลังลด" มาจากตัวหลัก
    ทั้งที่ SAP คิดราคาเต็ม ทำให้ตัวโชว์ที่มีของขึ้นเว็บด้วยราคาผิด

สิ่งที่ยังไม่ทำ (ตั้งใจ รอทีมยืนยัน):
  * ราคาสมาชิก (ZD52) — ยังไม่รู้ว่าลดจากราคาป้าย หรือลดซ้อนบนราคาปกติ ต่างกันหลายบาท
    ตอนนี้เก็บตัวเลขดิบไว้ใน snapshot แต่ยังไม่เขียนลงฐาน
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.integrations.sap.base import SapError
from app.integrations.sap.material_catalog import (
    BASE_KSCHL,
    DISPLAY_KSCHL,
    DISPLAY_VTWEG,
    MEMBER_KSCHL,
    ConditionLine,
    MaterialPriceRow,
    get_material_catalog_client,
)
from app.models.catalog import Material, MaterialPrice, ProductStock

log = logging.getLogger("sb.etl.prices")

SNAPSHOT_DIR = Path(__file__).resolve().parents[2] / "data" / "sap"
SNAPSHOT = SNAPSHOT_DIR / "material_prices.json"
KEEP_ARCHIVES = 14

# ช่วงรหัสที่เราขาย — ดูจาก materials จริง (19/20/25/59)
# ขอ 19 แล้ว SAP แถมตัวโชว์ 20 มาให้เอง จึงไม่ต้องขอ 20 แยก
# ซอยเป็นก้อนเพื่อไม่ให้ก้อนเดียวใหญ่จนหน่วยความจำบวมและ timeout
RANGES: list[tuple[str, str]] = [
    ("19000000", "19099999"),
    ("19100000", "19199999"),
    ("19200000", "19299999"),
    ("25000000", "25999999"),
    ("59000000", "59999999"),
]

# ส่วนลดตัวโชว์ (ZD06) อยู่คนละช่องทางจำหน่าย ต้องยิงเพิ่มอีกรอบเฉพาะช่วงรหัสตัวโชว์
DISPLAY_RANGE = ("20000000", "20999999")

# ราคาต่ำกว่านี้ถือว่ายังไม่ได้ตั้งราคา ไม่ใช่ของถูก (ตรงกับ import_catalog._fake_price)
MIN_REAL_PRICE = Decimal(10)

# ราคาขายที่ต่ำกว่าราคาป้ายมากขนาดนี้ ไม่น่าใช่ "โปรลดราคา" แต่เป็นราคาคนละความหมาย
#
# เจอของจริงตอนรันครั้งแรก: ชิ้นส่วนโซฟา 2L-PP ราคาป้าย 47,100 แต่ ZD39 ลดไป 37,990
# เหลือ 2,045 (4% ของป้าย) — ตัวเลขนี้คือราคาของ "ชิ้นส่วน" ในชุด ไม่ใช่ราคาขายแยกชิ้น
# ส่วนลดจริงที่พบในระบบหนักสุดประมาณ 40-50% ซึ่งยังผ่านด่านนี้ไปได้ปกติ
#
# ปล่อยผ่านแปลว่าเว็บขายโซฟา 47,100 ในราคา 2,045 — กันไว้ดีกว่า ให้คนดูก่อน
MIN_NET_RATIO = Decimal("0.10")

# รหัสขึ้นต้นของสองกลุ่ม — ตรงกับ catalog_matnr_groups (regular:19, display:20)
REGULAR_PREFIX = "19"
DISPLAY_PREFIX = "20"


def _q(v: Decimal | None) -> str | None:
    return None if v is None else str(v.quantize(Decimal("0.01")))


def fetch_all(ranges=RANGES) -> tuple[dict[str, MaterialPriceRow], list[str]]:
    client = get_material_catalog_client()
    out: dict[str, MaterialPriceRow] = {}
    problems: list[str] = []
    for lo, hi in ranges:
        t = time.time()
        try:
            rows = client.fetch_range(lo, hi)
        except SapError as e:
            # ก้อนเดียวพังไม่ควรล้มทั้งงาน — ราคาที่ดึงได้แล้วยังมีค่า
            problems.append(f"{lo}-{hi}: {e}")
            log.error("ช่วง %s-%s ไม่สำเร็จ: %s", lo, hi, e)
            continue
        for r in rows:
            out[r.matnr] = r
        log.info("ช่วง %s-%s: %s แถว (%.0f วิ)", lo, hi, f"{len(rows):,}", time.time() - t)

    # รอบสอง: ส่วนลดตัวโชว์ อยู่ช่องทางจำหน่าย 11 ไม่ใช่ 18 จึงไม่ติดมากับรอบแรก
    # เอาเฉพาะบรรทัด ZD06 มาแปะเพิ่มให้แถวเดิม ไม่แตะ PR01 ของรอบแรก
    lo, hi = DISPLAY_RANGE
    t = time.time()
    try:
        rows = client.fetch_range(lo, hi, vtweg=DISPLAY_VTWEG)
    except SapError as e:
        problems.append(f"ZD06 {lo}-{hi} (VTWEG {DISPLAY_VTWEG}): {e}")
        log.error("ดึงส่วนลดตัวโชว์ไม่สำเร็จ: %s", e)
        return out, problems
    n = 0
    for r in rows:
        zd = next((c for c in r.conditions if c.kschl == DISPLAY_KSCHL), None)
        if zd is None:
            continue
        # รหัสที่รอบแรกไม่เห็น (ตัวโชว์ที่ไม่มีคู่ 19) ก็เก็บไว้ พร้อมราคาป้ายของรอบนี้
        row = out.setdefault(r.matnr, MaterialPriceRow(matnr=r.matnr, name=r.name))
        if row.list_price is None and (base := r.of(BASE_KSCHL)) is not None:
            row.conditions.append(ConditionLine(BASE_KSCHL, base, "THB"))
        row.conditions.append(zd)
        n += 1
    log.info("ส่วนลดตัวโชว์ (VTWEG %s): %s รหัสมี %s (%.0f วิ)",
             DISPLAY_VTWEG, f"{n:,}", DISPLAY_KSCHL, time.time() - t)
    return out, problems


def display_of(matnr: str) -> str:
    """19210764 -> 20210764 · กติกาเดียวกับ sync_display_items.display_matnr"""
    return DISPLAY_PREFIX + matnr[len(REGULAR_PREFIX):]


def _entry(r: MaterialPriceRow) -> dict:
    return {
        "name": r.name,
        "list": _q(r.list_price),
        "net": _q(r.net_price()),
        # เก็บบรรทัดส่วนลดดิบไว้ด้วย — สูตรเปลี่ยนเมื่อไรคำนวณใหม่จากไฟล์นี้ได้ ไม่ต้องยิง SAP
        "discounts": [{"kschl": c.kschl, "value": str(c.value), "unit": c.unit}
                      for c in r.conditions if c.kschl != BASE_KSCHL],
    }


def build_snapshot(rows: dict[str, MaterialPriceRow], ours: set[str], problems: list[str]) -> dict:
    """แยกเป็นสองกอง ตามที่เอาไปใช้จริง

    regular (19xxx)  เก็บรหัส + ราคา + ส่วนลดที่ติดมา ไว้อ้างอิงเฉยๆ
                     ราคาขายของกลุ่มนี้ sb_products คิดมาเรียบร้อยแล้ว งานนี้ไม่แตะ
    display (20xxx)  ราคาที่คำนวณเสร็จแล้ว พร้อมเอาไปใส่ฐาน — นี่คือของที่ต้องใช้จริง
                     ส่วนใหญ่ไม่มีส่วนลด = ราคาป้ายเต็ม · ที่มีส่วนลดก็คิดให้แล้วใน net

    ทั้งสองกองเป็น dict ที่คีย์คือรหัสสินค้า เปิดไฟล์แล้วหยิบใช้ได้ทันทีโดยไม่ต้องไล่ลูป
    """
    s = get_settings()
    regular: dict[str, dict] = {}
    display: dict[str, dict] = {}
    for code in sorted(ours & rows.keys()):
        r = rows[code]
        if code.startswith(DISPLAY_PREFIX):
            e = _entry(r)
            twin = REGULAR_PREFIX + code[len(DISPLAY_PREFIX):]
            e["pair"] = twin if twin in rows else None   # ตัวหลักที่ตัวโชว์นี้พ่วงมา
            # ZD06 = "ส่วนลดตัวโชว์" · มีบรรทัดนี้เท่านั้นถึงจะเอาขึ้นเว็บ (กติกาจากทีมขาย)
            zd = r.of(DISPLAY_KSCHL)
            e["zd06"] = None if zd is None else str(zd)
            e["sellable"] = zd is not None
            display[code] = e
        else:
            regular[code] = _entry(r)
    missing = sorted(ours - rows.keys())
    with_disc = sum(1 for e in display.values() if e["discounts"])
    return {
        "_note": [
            "ราคาสินค้าจาก SAP — สร้างโดย python -m app.etl.sync_sap_prices · อย่าแก้ด้วยมือ",
            "net = ราคาป้าย ลดเปอร์เซ็นต์ก่อน แล้วค่อยหักส่วนลดที่เป็นบาท (ไม่รวมส่วนลดสมาชิก)",
            "ยืนยันกับของจริง: 5,490 x (1 - 20%) - 2 = 4,390 ตรงกับราคาที่ขายอยู่",
            "",
            "regular (19xxx) = เก็บไว้อ้างอิงเท่านั้น ไม่เอาไปเขียนทับฐาน",
            "                  ราคาขายของกลุ่มนี้มาจาก sb_products ซึ่งคิดมาถูกแล้ว",
            "display (20xxx) = ราคาที่คำนวณเสร็จแล้ว เอาไปใส่ฐานได้เลย · pair บอกว่าพ่วงมากับตัวไหน",
            "                  sellable=true คือมี ZD06 (ส่วนลดตัวโชว์) — เฉพาะพวกนี้ที่ขึ้นเว็บ",
            "                  ZD06 อยู่ช่องทางจำหน่าย 11 ไม่ใช่ช่องทางราคาปกติ จึงต้องยิง SAP สองรอบ",
            "",
            f"{MEMBER_KSCHL} (ส่วนลดสมาชิก) เก็บไว้ใน discounts แต่ยังไม่คำนวณ รอทีมยืนยันสูตร",
        ],
        "source": {
            "function": "ZAIBAPI_MATERIAL_GET_ALL",
            "sales_org": str(s.sap_sales_org),
            "distr_chan": str(s.sap_distr_chan),
            "division": str(s.sap_division),
            "ranges": [f"{lo}-{hi}" for lo, hi in RANGES],
        },
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "condition_types": {
            BASE_KSCHL: "ราคาป้าย รวมภาษี (ฐานตั้งต้น)",
            "ZD01": "ส่วนลด Standard (%)",
            "ZD39": "ส่วนลด Standard (บาท)",
            MEMBER_KSCHL: "ส่วนลด Member (%) — ยังไม่ใช้",
            "ZD36": "ส่วนลดชุด Set-Main 59 (บาท)",
            "ZD18": "ส่วนลด GP (%)",
            "ZD35": "ส่วนลดโปรโมชั่น-Mer (บาท)",
            "ZD38": "ส่วนลดโปรเพิ่ม (บาท)",
        },
        "stats": {
            "from_sap": len(rows),
            "ours": len(ours),
            "regular": len(regular),
            "display": len(display),
            "display_with_discount": with_disc,
            "display_sellable": sum(1 for e in display.values() if e["sellable"]),
            "missing_in_sap": len(missing),
        },
        # รหัสที่เรามีแต่ SAP ไม่รู้จัก — ส่งให้ทีมสินค้าตรวจ (เก็บตัวอย่าง 500 ตัวพอ)
        "missing_in_sap": missing[:500],
        "problems": problems,
        "regular": regular,
        "display": display,
    }


def write_snapshot(snap: dict) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    stamp = datetime.now().strftime("%Y%m%d")
    (SNAPSHOT_DIR / f"material_prices_{stamp}.json").write_text(
        json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    for f in sorted(SNAPSHOT_DIR.glob("material_prices_2*.json"))[:-KEEP_ARCHIVES]:
        f.unlink(missing_ok=True)
    return SNAPSHOT


def apply_to_db(snap: dict, dry_run: bool, allow_deep: bool = False) -> dict:
    """เขียนราคาตัวโชว์ (20xxx) ลงฐาน — ไม่แตะสินค้าปกติ (19xxx)

    ที่ไม่แตะ 19 เพราะราคาขายของกลุ่มนั้นมาจาก sb_products ซึ่งคิดส่วนลดมาเรียบร้อยแล้ว
    มาคิดใหม่จาก A004 เองมีแต่จะทำให้สองที่ไม่ตรงกัน · snapshot เก็บ 19 ไว้อ้างอิงอยู่แล้ว

    ของที่แก้จริงคือ 20xxx ซึ่งเดิมก๊อปราคา "หลังลด" มาจากตัวหลัก ทั้งที่ SAP คิดราคาเต็ม
    """
    changed: list[tuple[str, str, str, str]] = []
    suspicious: list[tuple[str, str, str, str]] = []
    added = skipped = 0
    in_stock_changed = 0
    with SessionLocal() as db:
        existing = {(p.matnr, p.tier): p for p in db.scalars(
            select(MaterialPrice).where(MaterialPrice.tier.in_(("standard", "compare_at"))))}
        # ตัวที่มีของจริง = ตัวที่ขึ้นหน้าเว็บ ราคาผิดตรงนี้คือลูกค้าเห็นผิดทันที
        stocked = {s_.matnr for s_ in db.scalars(select(ProductStock).where(ProductStock.ready_qty > 0))}
        for code, m in snap["display"].items():
            net = None if m["net"] is None else Decimal(m["net"])
            lst = None if m["list"] is None else Decimal(m["list"])
            if net is None or net <= MIN_REAL_PRICE:
                skipped += 1           # ยังไม่ตั้งราคาใน SAP — อย่าทับของเดิมด้วยเลขหลอก
                continue
            # ถูกผิดปกติเมื่อเทียบกับราคาป้ายตัวเอง — กันไว้ให้คนดูก่อน (ดู MIN_NET_RATIO)
            if lst and lst > 0 and net / lst < MIN_NET_RATIO and not allow_deep:
                suspicious.append((code, m["name"], str(lst), str(net)))
                continue
            hit = False
            for tier, value in (("standard", net), ("compare_at", lst)):
                if value is None:
                    continue
                row = existing.get((code, tier))
                if row is None:
                    added += 1
                    hit = True
                    if not dry_run:
                        db.add(MaterialPrice(matnr=code, tier=tier, price=value))
                elif Decimal(str(row.price)) != value:
                    changed.append((code, tier, str(row.price), str(value)))
                    hit = True
                    if not dry_run:
                        row.price = value
            if hit and code in stocked:
                in_stock_changed += 1
        if not dry_run:
            db.commit()
    return {"added": added, "changed": changed, "skipped_no_price": skipped,
            "suspicious": suspicious, "in_stock_changed": in_stock_changed,
            "stocked_total": len(stocked)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ดึงราคาจาก SAP แล้วอัปเดตฐาน (งานรายวัน)")
    ap.add_argument("--dry-run", action="store_true", help="ดูผลอย่างเดียว ไม่เขียนฐาน")
    ap.add_argument("--from-file", action="store_true", help="ใช้ snapshot เดิม ไม่ยิง SAP")
    ap.add_argument("--allow-deep-discount", action="store_true",
                    help="ยอมรับราคาที่ต่ำกว่า 10%% ของราคาป้ายด้วย (ปกติกันไว้ ดู MIN_NET_RATIO)")
    ap.add_argument("--limit-changes", type=int, default=15, help="จำนวนบรรทัดตัวอย่างที่พิมพ์")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")

    if a.from_file:
        if not SNAPSHOT.exists():
            print(f"! ยังไม่มี {SNAPSHOT} — รันโดยไม่ใส่ --from-file ก่อน")
            return 1
        snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        log.info("ใช้ snapshot เดิมจาก %s", snap["fetched_at"])
    else:
        with SessionLocal() as db:
            ours = {m for (m,) in db.execute(select(Material.matnr))}
        log.info("สินค้าในฐานเรา %s รายการ — เริ่มดึงราคาจาก SAP", f"{len(ours):,}")
        t = time.time()
        rows, problems = fetch_all()
        if not rows:
            print("! ดึงจาก SAP ไม่ได้เลยสักช่วง ไม่เขียนทับ snapshot เดิม")
            for p in problems:
                print("   ", p)
            return 1
        snap = build_snapshot(rows, ours, problems)
        write_snapshot(snap)
        log.info("ดึงเสร็จใน %.0f วิ -> %s", time.time() - t, SNAPSHOT)

    st = snap["stats"]
    print(f"\nSAP ส่งมา {st['from_sap']:,} · เราขาย {st['ours']:,}"
          f"\n  สินค้าปกติ 19xxx {st['regular']:,} — เก็บไว้อ้างอิง ไม่แตะฐาน"
          f"\n  ตัวโชว์  20xxx {st['display']:,} — มี ZD06 (ขึ้นเว็บได้) {st.get('display_sellable', 0):,}"
          f"\n  SAP ไม่รู้จักรหัสนี้ {st['missing_in_sap']:,}")
    for p in snap.get("problems") or []:
        print("   ดึงไม่สำเร็จ:", p)

    res = apply_to_db(snap, a.dry_run, a.allow_deep_discount)
    head = "[ซ้อม] " if a.dry_run else ""
    print(f"{head}เพิ่มใหม่ {res['added']:,} · ราคาเปลี่ยน {len(res['changed']):,}"
          f" · ข้ามเพราะยังไม่ตั้งราคา {res['skipped_no_price']:,}")
    if res["suspicious"]:
        print(f"\n  ** ถูกผิดปกติ {len(res['suspicious']):,} รายการ — ไม่เขียนลงฐาน รอคนตรวจ **")
        print("     (ราคาขายต่ำกว่า 10% ของราคาป้าย มักเป็นราคา 'ชิ้นส่วนในชุด' ไม่ใช่ราคาขายแยก)")
        for code, name, lst, net in res["suspicious"][:8]:
            print(f"    {code:<11} {name[:40]:<42} {lst:>10} -> {net:>9}")
        if len(res["suspicious"]) > 8:
            print(f"    … อีก {len(res['suspicious']) - 8:,} รายการ")
    print(f"  ในนั้นเป็นตัวโชว์ที่มีของพร้อมขาย {res['in_stock_changed']:,} รายการ"
          f" (ตัวโชว์ที่มีของทั้งหมด {res['stocked_total']:,}) — พวกนี้ขึ้นหน้าเว็บจริง")
    for code, tier, was, now in res["changed"][:a.limit_changes]:
        print(f"    {code:<12} {tier:<11} {was:>12} -> {now:>12}")
    if len(res["changed"]) > a.limit_changes:
        print(f"    … อีก {len(res['changed']) - a.limit_changes:,} รายการ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
