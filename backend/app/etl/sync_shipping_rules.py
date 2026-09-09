"""ดึงกฎค่าส่งจาก Magento (10.9.12.67) มาคลีนแล้วลง ship_rates / ship_rules / ship_product_attrs

    python -m app.etl.sync_shipping_rules --report-only     # ดูรายงานการคลีนก่อน ไม่เขียนอะไร
    python -m app.etl.sync_shipping_rules --out rates.csv   # ดัมป์ตารางที่คลีนแล้วออกไฟล์
    python -m app.etl.sync_shipping_rules                   # เขียนจริง (ล้างของเดิมแล้วใส่ใหม่)
    python -m app.etl.sync_shipping_rules --skip-attrs      # ไม่ต้องดึงธงรายสินค้า 42,000 แถว

อ่านจาก Magento อย่างเดียว ไม่แตะอะไรฝั่งนั้น · ฝั่งเราเป็นการแทนที่ทั้งตาราง
(ตาราง ship_* เป็นข้อมูลอนุพันธ์ทั้งหมด แก้มือแล้ว sync รอบหน้าจะถูกทับ)

ทำไมต้องคลีน — ต้นทางเป็นตารางอัตราที่ถูกยัดเป็น rule 207 ตัว แก้กันมาหลายรอบจนมี:
  · แถวซ้ำเป๊ะ (62.01-63 มี 4 แถว)
  · ช่วงหยาบของเก่าคร่อมช่วงละเอียดของใหม่ (5.01-10 คร่อม 6.01-7, 7.01-8, ...)
  · ช่วงกลับหัว (rule 409: >= 49.01 และ <= 41) ซึ่งแมตช์ไม่ได้เลย
  · ปน <= กับ < ทำให้ของที่หนัก 1.01 kg เป๊ะ ตกร่องระหว่างแถว
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from decimal import Decimal

from sqlalchemy import create_engine, delete, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.shipping import ShipArea, ShipAreaPostcode, ShipProductAttr, ShipRate, ShipRule

for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "encoding", "") and _s.encoding.lower() not in ("utf-8", "utf8"):
        _s.reconfigure(encoding="utf-8", errors="replace")

AREAS = [
    (1, "bkk_metro", "กรุงเทพฯ และปริมณฑล", False),
    (2, "upcountry", "ต่างจังหวัด", True),  # ไม่เข้า prefix ไหน = ต่างจังหวัด
]
# กทม. + สมุทรปราการ ใช้ 10xxx ร่วมกัน · นนทบุรี 11 · ปทุมธานี 12 · นครปฐม 73 · สมุทรสาคร 74
AREA_POSTCODES = [("10", 1, "กรุงเทพฯ + สมุทรปราการ"), ("11", 1, "นนทบุรี"), ("12", 1, "ปทุมธานี"), ("73", 1, "นครปฐม"), ("74", 1, "สมุทรสาคร")]

FLAGS = ("flat_pack", "flatpack_not_seller", "flat_pack_bulky", "attr_19_rule", "attr_25_rule")
WEIGHT_SENTINELS = (Decimal("999"), Decimal("0"))  # 934 ตัวใส่ 999 · 6,248 ตัวใส่ 0 ทั้งคู่แปลว่า "ไม่ได้กรอก"
TOP_WEIGHT = Decimal("99999")


# ---------------------------------------------------------------- อ่านจาก Magento

def _walk(node: dict, out: dict) -> None:
    t = (node.get("type") or "").split("\\")[-1]
    attr, op, val = node.get("attribute"), node.get("operator"), node.get("value")
    if t == "Area":
        out["area"] = int(val)
    elif attr == "row_weight":
        out.setdefault("weight", []).append((op, Decimal(str(val))))
    elif attr in ("package_value_with_discount", "package_value"):
        out.setdefault("subtotal", []).append((op, Decimal(str(val))))
    elif attr == "sku" and op == "()":
        out["any_sku"] = [s.strip() for s in str(val).split(",") if s.strip()]
    elif t == "Product" and attr:
        out.setdefault("item_clauses", []).append({"attr": attr, "op": _op(op), "value": str(val)})
    elif attr and attr != "base_row_total_incl_tax":
        out.setdefault("unknown", []).append(f"{attr}{op}{val}")
    for sub in node.get("conditions") or []:
        _walk(sub, out)


def _op(op: str) -> str:
    return {"!{}": "!contains", "{}": "contains"}.get(op, op)


def fetch_rules() -> list[dict]:
    url = get_settings().magento_url
    if not url:
        raise SystemExit("! ไม่ได้ตั้งค่าเชื่อมต่อ Magento ใน .env (MAGENTO_HOST/USER/PASSWORD)")
    eng = create_engine(url, connect_args={"connect_timeout": 10})
    with eng.connect() as c:
        c.execute(text("SET NAMES utf8mb4"))
        rows = c.execute(text(
            "SELECT rule_id, name, pos, rate_base, skip_subsequent, conditions_serialized"
            " FROM amasty_shiprules_rule WHERE is_active = 1 ORDER BY pos, rule_id"
        )).fetchall()
    eng.dispose()
    out = []
    for rid, name, pos, rate, skip, cond in rows:
        parsed: dict = {}
        try:
            _walk(json.loads(cond or "{}"), parsed)
        except (ValueError, TypeError) as e:
            parsed = {"unknown": [f"อ่าน JSON ไม่ได้: {type(e).__name__}"]}
        out.append({"rule_id": rid, "name": (name or "").strip(), "pos": int(pos or 0),
                    "fee": Decimal(str(rate or 0)), "skip": bool(skip), "parsed": parsed})
    return out


def fetch_product_attrs() -> tuple[dict[str, dict], list[str]]:
    """sku → {weight_kg, ธง 5 ตัว} จาก EAV · store_id=0 คือค่าเริ่มต้นของสินค้า"""
    eng = create_engine(get_settings().magento_url, connect_args={"connect_timeout": 20})
    log: list[str] = []
    data: dict[str, dict] = {}
    with eng.connect() as c:
        c.execute(text("SET NAMES utf8mb4"))
        meta = {r[1]: (r[0], r[2]) for r in c.execute(text(
            "SELECT a.attribute_id, a.attribute_code, a.backend_type FROM eav_attribute a"
            " JOIN eav_entity_type e ON e.entity_type_id = a.entity_type_id"
            " WHERE e.entity_type_code = 'catalog_product' AND a.attribute_code IN :codes"
        ), {"codes": ("weight",) + FLAGS}).fetchall()}
        for code in ("weight",) + FLAGS:
            if code not in meta:
                log.append(f"! ไม่พบ attribute {code} ใน Magento — ข้ามไป")
                continue
            aid, btype = meta[code]
            rows = c.execute(text(
                f"SELECT cpe.sku, v.value FROM catalog_product_entity cpe"
                f" JOIN catalog_product_entity_{btype} v ON v.entity_id = cpe.entity_id"
                f" WHERE v.attribute_id = :aid AND v.store_id = 0 AND v.value IS NOT NULL"
            ), {"aid": aid}).fetchall()
            n = 0
            for sku, val in rows:
                sku = (sku or "").strip()
                if not sku:
                    continue
                rec = data.setdefault(sku, {})
                if code == "weight":
                    w = Decimal(str(val))
                    if w in WEIGHT_SENTINELS or w <= 0:
                        continue  # ค่าที่ใส่ไว้กันช่องว่าง ไม่ใช่น้ำหนักจริง
                    rec["weight_kg"] = w
                else:
                    rec[code] = str(val).strip() == "1"
                n += 1
            log.append(f"   {code}: {len(rows):,} แถวใน Magento · ใช้ได้ {n:,}")
    eng.dispose()
    return data, log


# ---------------------------------------------------------------- คลีนตารางอัตรา

def build_rates(rules: list[dict]) -> tuple[list[dict], list[str]]:
    """แปลง rule ตารางอัตรา → ช่วงครึ่งเปิด [from, to) ที่ไม่ซ้อน ไม่ขาด"""
    log: list[str] = []
    raw: list[dict] = []
    for r in rules:
        p = r["parsed"]
        if "weight" not in p or "area" not in p:
            continue
        lo = next((v for op, v in p["weight"] if op.startswith(">")), None)
        hi = next((v for op, v in p["weight"] if op.startswith("<")), None)
        if lo is None or hi is None:
            log.append(f"ข้าม rule {r['rule_id']}: อ่านช่วงน้ำหนักไม่ครบ")
            continue
        raw.append({"area": p["area"], "lo": lo, "hi": hi, "fee": r["fee"], "rule_id": r["rule_id"], "note": None})
    log.append(f"อ่านช่วงน้ำหนักจากต้นทางได้ {len(raw)} แถว")

    out: list[dict] = []
    for area in sorted({b["area"] for b in raw}):
        bands = [b for b in raw if b["area"] == area]
        bands, l1 = _dedupe(bands)
        bands, l2 = _repair_reversed(bands)
        bands, l3 = _close_gaps(bands)
        log += [f"เขต {area}: {m}" for m in l1 + l2 + l3]
        log.append(f"เขต {area}: เหลือ {len(bands)} ช่วง (จาก {len([b for b in raw if b['area'] == area])})")
        out += bands
    return out, log


def _dedupe(bands: list[dict]) -> tuple[list[dict], list[str]]:
    """ตัดแถวซ้ำเป๊ะ แล้วตัดช่วงที่ถูกช่วงอื่นคร่อมอยู่และค่าส่งเท่ากัน (ช่วงกว้างชนะ)"""
    log: list[str] = []
    seen: dict[tuple, dict] = {}
    for b in sorted(bands, key=lambda x: x["rule_id"]):
        key = (b["lo"], b["hi"], b["fee"])
        if key in seen:
            log.append(f"ซ้ำ: rule {b['rule_id']} เหมือน rule {seen[key]['rule_id']} ({b['lo']}-{b['hi']} = {b['fee']})")
            continue
        seen[key] = b
    kept = list(seen.values())
    drop: set[int] = set()
    for a in kept:
        for b in kept:
            if a is b or b["rule_id"] in drop or a["lo"] > a["hi"] or b["lo"] > b["hi"]:
                continue
            covered = a["lo"] <= b["lo"] and a["hi"] >= b["hi"] and (a["lo"], a["hi"]) != (b["lo"], b["hi"])
            if not covered:
                continue
            if a["fee"] == b["fee"]:
                drop.add(b["rule_id"])
                log.append(f"ยุบ: rule {b['rule_id']} ({b['lo']}-{b['hi']}) อยู่ในช่วง rule {a['rule_id']} ({a['lo']}-{a['hi']}) ค่าส่งเท่ากัน {a['fee']}")
            else:
                drop.add(a["rule_id"])
                log.append(f"! ค่าส่งขัดกัน: rule {a['rule_id']} ({a['lo']}-{a['hi']} = {a['fee']}) คร่อม rule {b['rule_id']} ({b['lo']}-{b['hi']} = {b['fee']}) — เก็บช่วงที่แคบกว่า")
    return [b for b in kept if b["rule_id"] not in drop], log


def _repair_reversed(bands: list[dict]) -> tuple[list[dict], list[str]]:
    """ช่วงกลับหัว (from > to) เกิดจากพิมพ์เลขต้นผิด — ถ้าปลายช่วงตกอยู่ในรูของตาราง ให้ยึดปลายเป็นหลัก"""
    log: list[str] = []
    ok = sorted([b for b in bands if b["lo"] <= b["hi"]], key=lambda x: x["lo"])
    fixed: list[dict] = []
    for b in [x for x in bands if x["lo"] > x["hi"]]:
        prev = [x for x in ok if x["hi"] < b["hi"]]
        nxt = [x for x in ok if x["lo"] > b["hi"]]
        if prev and nxt and nxt[0]["lo"] > prev[-1]["hi"]:
            old_lo, b["lo"] = b["lo"], prev[-1]["hi"]
            b["note"] = f"ซ่อมช่วงกลับหัว (ต้นทางเขียนต้นช่วง {old_lo})"
            log.append(f"ซ่อม: rule {b['rule_id']} ต้นช่วง {old_lo} → {b['lo']} (ช่วงเป็น {b['lo']}-{b['hi']} = {b['fee']})")
            fixed.append(b)
        else:
            log.append(f"! ทิ้ง rule {b['rule_id']}: ช่วงกลับหัว {b['lo']}-{b['hi']} และเดาต้นช่วงไม่ได้")
    return sorted(ok + fixed, key=lambda x: x["lo"]), log


def _close_gaps(bands: list[dict]) -> tuple[list[dict], list[str]]:
    """ทำให้ต่อเนื่องเป็นครึ่งเปิด: ปลายของแถวก่อนหน้า = ต้นของแถวถัดไป · แถวสุดท้ายเปิดถึงเพดาน"""
    log: list[str] = []
    bands = sorted(bands, key=lambda x: (x["lo"], x["hi"]))
    for i, b in enumerate(bands):
        nxt = bands[i + 1] if i + 1 < len(bands) else None
        new_hi = nxt["lo"] if nxt else TOP_WEIGHT
        # รอยต่อ 0.01 (แถวก่อนจบที่ 3 แถวถัดไปเริ่ม 3.01) เป็นแค่ผลของการเขียน <= ไม่ใช่รูจริง — ไม่ต้องรายงาน
        if nxt and nxt["lo"] - b["hi"] > Decimal("0.011"):
            log.append(f"ปิดช่องว่าง {b['hi']} → {nxt['lo']} ด้วยค่าส่งของ rule {b['rule_id']} ({b['fee']})")
        b["hi"] = new_hi
    if bands:
        log.append(f"แถวสุดท้าย (rule {bands[-1]['rule_id']}) เปิดถึง {TOP_WEIGHT} kg = {bands[-1]['fee']}")
    return bands, log


# ---------------------------------------------------------------- แปลงกฎที่ไม่ใช่ตาราง

def build_rules(rules: list[dict]) -> tuple[list[dict], list[str]]:
    log: list[str] = []
    out: list[dict] = []
    seen: dict[str, int] = {}
    for r in rules:
        p = r["parsed"]
        if "weight" in p:
            continue  # เป็นแถวของตารางอัตรา จัดการที่ build_rates แล้ว
        if p.get("unknown"):
            log.append(f"! ข้าม rule {r['rule_id']} ({r['name']}): มีเงื่อนไขที่ยังไม่รองรับ {p['unknown']}")
            continue
        cond: dict = {}
        for op, v in p.get("subtotal", []):
            cond["min_subtotal" if op.startswith(">") else "max_subtotal"] = float(v)
        if "any_sku" in p:
            cond["any_sku"] = p["any_sku"]
        if "item_clauses" in p:
            cond["require_item_all_of"] = p["item_clauses"]
        if not cond:
            log.append(f"! ข้าม rule {r['rule_id']} ({r['name']}): ไม่มีเงื่อนไขเลย จะแมตช์ทุกตะกร้า")
            continue
        sig = json.dumps(cond, sort_keys=True, ensure_ascii=False) + f"|{r['fee']}"
        if sig in seen:
            log.append(f"ซ้ำ: rule {r['rule_id']} ({r['name']}) เหมือน rule {seen[sig]} ทุกอย่าง")
            continue
        seen[sig] = r["rule_id"]
        stop = r["skip"]
        if not stop and r["fee"] == 0:
            # ต้นทางตั้ง skip_subsequent=0 ไว้กับกฎส่งฟรีเฉพาะ SKU ทำให้กฎเรตเดียวมาทับเป็น 399 ทีหลัง
            # ซึ่งขัดกับชื่อกฎเอง ("ส่งฟรี") — ฝั่งเราให้หยุดเมื่อแมตช์
            stop = True
            log.append(f"ปรับ: rule {r['rule_id']} ({r['name']}) เป็นหยุดเมื่อแมตช์ ไม่งั้นกฎถัดไปทับค่าส่งฟรีเป็นเรตเดียว")
        out.append({"code": f"amasty-{r['rule_id']}", "name": r["name"], "kind": "free" if r["fee"] == 0 else "flat",
                    "priority": r["pos"], "stop_on_match": stop, "fee": r["fee"], "conditions": cond,
                    "source_rule_id": r["rule_id"]})
    # ไม่เหมือนกันเป๊ะแต่ลำดับและค่าส่งเท่ากัน = รุ่นเก่าที่ลืมปิด ตัวที่ rule_id น้อยกว่าชนะเสมอ
    # ทิ้งไว้ไม่ได้ผิด แต่คนดูแลควรรู้ว่ามีของซ้อนอยู่
    for i, a in enumerate(out):
        for b in out[i + 1:]:
            if (a["priority"], a["fee"], a["stop_on_match"]) == (b["priority"], b["fee"], b["stop_on_match"]) and a["conditions"] != b["conditions"]:
                log.append(f"? ใกล้เคียงกัน: rule {a['source_rule_id']} กับ {b['source_rule_id']} ลำดับ {a['priority']} ค่าส่ง {a['fee']} เท่ากัน ต่างกันแค่เงื่อนไข — {a['source_rule_id']} ชนะเสมอ")
    return out, log


def table_rule(rates: list[dict]) -> dict:
    """กฎเดียวที่ชี้ไปที่ตารางอัตรา — ต้นทางกระจายเป็น rule 207 ตัวเพราะไม่มีที่เก็บตาราง"""
    areas = sorted({b["area"] for b in rates})
    return {"code": "weight-table", "name": f"ตารางน้ำหนัก {len(rates)} ช่วง · เขต {areas}", "kind": "table",
            "priority": 3, "stop_on_match": True, "fee": Decimal(0),
            "conditions": {"weight_attr": "flatpack_not_seller"}, "source_rule_id": None}


# ---------------------------------------------------------------- เขียนลงฐานของแอป

def write_all(db: Session, rates: list[dict], rules: list[dict], attrs: dict[str, dict] | None) -> list[str]:
    log: list[str] = []
    for aid, code, name, is_def in AREAS:
        row = db.get(ShipArea, aid) or ShipArea(id=aid)
        row.code, row.name, row.is_default = code, name, is_def
        db.add(row)
    for prefix, aid, note in AREA_POSTCODES:
        row = db.get(ShipAreaPostcode, prefix) or ShipAreaPostcode(prefix=prefix)
        row.area_id, row.note = aid, note
        db.add(row)
    db.flush()

    db.execute(delete(ShipRate))
    for b in rates:
        db.add(ShipRate(area_id=b["area"], weight_from=b["lo"], weight_to=b["hi"], fee=b["fee"],
                        source_rule_id=b["rule_id"], note=b.get("note")))
    log.append(f"ship_rates: {len(rates)} แถว")

    db.execute(delete(ShipRule))
    for r in rules:
        db.add(ShipRule(code=r["code"], name=r["name"], kind=r["kind"], priority=r["priority"],
                        stop_on_match=r["stop_on_match"], fee=r["fee"], conditions=r["conditions"],
                        is_active=True, source_rule_id=r["source_rule_id"]))
    log.append(f"ship_rules: {len(rules)} กฎ")

    if attrs is not None:
        db.execute(delete(ShipProductAttr))
        db.flush()
        db.bulk_save_objects([
            ShipProductAttr(sku=sku, weight_kg=v.get("weight_kg"), **{f: bool(v.get(f)) for f in FLAGS})
            for sku, v in attrs.items()
        ])
        log.append(f"ship_product_attrs: {len(attrs):,} sku")
    db.commit()
    return log


# ---------------------------------------------------------------- เขียนลงฐานเว็บ (10.9.11.111)

# ตาราง sb_ship_* เป็นสำเนาของข้อมูลอนุพันธ์ล้วน — ล้างแล้วใส่ใหม่ทั้งชุดทุกรอบ
# ไม่ใช้ upsert เพราะกฎ/ช่วงน้ำหนักที่ต้นทางลบทิ้ง ต้องหายไปจากสำเนาด้วย ไม่งั้นค้างเป็นผี
SBWEB_TABLES = ("sb_ship_rates", "sb_ship_rules", "sb_ship_product_attrs", "sb_ship_area_postcodes", "sb_ship_areas")
CHUNK = 2000


def upsert_sbweb(rates: list[dict], rules: list[dict], attrs: dict[str, dict] | None) -> list[str]:
    url = get_settings().sbweb_database_url
    if not url:
        raise SystemExit("! ไม่ได้ตั้ง SBWEB_DATABASE_URL ใน .env (ฐานเว็บ 10.9.11.111)")
    log: list[str] = []
    eng = create_engine(url, pool_pre_ping=True)
    with eng.connect() as c:
        raw = c.connection
        cur = raw.cursor()
        # ธงรายสินค้าเป็นชุดใหญ่ที่สุด ถ้า --skip-attrs ห้ามล้างของเดิมทิ้ง
        for t in SBWEB_TABLES:
            if t == "sb_ship_product_attrs" and attrs is None:
                continue
            cur.execute(f"DELETE FROM {t}")

        cur.executemany(
            "INSERT INTO sb_ship_areas (id, code, name, is_default) VALUES (%s, %s, %s, %s)",
            [(aid, code, name, int(is_def)) for aid, code, name, is_def in AREAS],
        )
        cur.executemany(
            "INSERT INTO sb_ship_area_postcodes (prefix, area_id, note) VALUES (%s, %s, %s)",
            [(p, aid, note) for p, aid, note in AREA_POSTCODES],
        )
        cur.executemany(
            "INSERT INTO sb_ship_rates (area_id, weight_from, weight_to, fee, source_rule_id, note) VALUES (%s, %s, %s, %s, %s, %s)",
            [(b["area"], b["lo"], b["hi"], b["fee"], b["rule_id"], b.get("note")) for b in rates],
        )
        log.append(f"sb_ship_rates: {len(rates)} แถว")
        cur.executemany(
            "INSERT INTO sb_ship_rules (code, name, kind, priority, stop_on_match, fee, conditions, is_active, source_rule_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s)",
            [(r["code"], r["name"], r["kind"], r["priority"], int(r["stop_on_match"]), r["fee"],
              json.dumps(r["conditions"], ensure_ascii=False) if r["conditions"] else None, r["source_rule_id"]) for r in rules],
        )
        log.append(f"sb_ship_rules: {len(rules)} กฎ")

        if attrs is not None:
            data = [(sku, v.get("weight_kg"), *[int(bool(v.get(f))) for f in FLAGS]) for sku, v in attrs.items()]
            sql = (f"INSERT INTO sb_ship_product_attrs (matnr, weight_kg, {', '.join(FLAGS)})"
                   f" VALUES ({', '.join(['%s'] * (len(FLAGS) + 2))})")
            for i in range(0, len(data), CHUNK):
                cur.executemany(sql, data[i : i + CHUNK])
            log.append(f"sb_ship_product_attrs: {len(data):,} sku")
        raw.commit()
    return log


def dump_csv(path: str, rates: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["area", "weight_from", "weight_to", "fee", "source_rule_id", "note"])
        for b in sorted(rates, key=lambda x: (x["area"], x["lo"])):
            w.writerow([b["area"], b["lo"], b["hi"], b["fee"], b["rule_id"], b.get("note") or ""])


def main() -> int:
    ap = argparse.ArgumentParser(description="ดึงกฎค่าส่งจาก Magento มาคลีนแล้วลงตารางของเรา")
    ap.add_argument("--report-only", action="store_true", help="ดูรายงานอย่างเดียว ไม่เขียนฐาน")
    ap.add_argument("--skip-attrs", action="store_true", help="ไม่ต้องดึงธงรายสินค้า (เร็วขึ้นมากตอนทดสอบ)")
    ap.add_argument("--out", help="ดัมป์ตารางที่คลีนแล้วเป็น CSV")
    ap.add_argument("--no-sbweb", action="store_true", help="ข้ามการเขียนฐานเว็บ ลงเฉพาะฐานแอป")
    args = ap.parse_args()

    src = fetch_rules()
    print(f"อ่านกฎที่เปิดใช้จาก Magento ได้ {len(src)} ข้อ\n")
    rates, rate_log = build_rates(src)
    rules, rule_log = build_rules(src)
    if rates:
        rules.append(table_rule(rates))

    print("== คลีนตารางอัตรา ==")
    for line in rate_log:
        print("  ", line)
    print("\n== กฎที่ไม่ใช่ตาราง ==")
    for line in rule_log:
        print("  ", line)
    for r in sorted(rules, key=lambda x: x["priority"]):
        print(f"   [{r['priority']}] {r['code']:<14} {r['kind']:<5} {r['fee']:>8} {'หยุด' if r['stop_on_match'] else 'ไปต่อ'}  {r['name']}")

    attrs = None
    if not args.skip_attrs:
        print("\n== ธงรายสินค้า ==")
        attrs, attr_log = fetch_product_attrs()
        for line in attr_log:
            print(line)
        n_w = sum(1 for v in attrs.values() if v.get("weight_kg"))
        n_f = sum(1 for v in attrs.values() if v.get("flatpack_not_seller"))
        print(f"   รวม {len(attrs):,} sku · มีน้ำหนักใช้ได้ {n_w:,} · flatpack_not_seller=1 {n_f:,}")

    if args.out:
        dump_csv(args.out, rates)
        print(f"\nเขียน CSV: {args.out}")

    if args.report_only:
        print("\n(--report-only: ไม่ได้เขียนฐาน)")
        return 0
    if not args.no_sbweb:
        print("\n== ฐานเว็บ 10.9.11.111 ==")
        for line in upsert_sbweb(rates, rules, attrs):
            print("  ", line)
    print("\n== ฐานแอป ==")
    with SessionLocal() as db:
        for line in write_all(db, rates, rules, attrs):
            print("  ", line)
    print("\nเสร็จ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
