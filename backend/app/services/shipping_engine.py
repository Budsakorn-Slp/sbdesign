"""คิดค่าส่งจากตารางของเราเอง (ship_rules + ship_rates) พร้อมร่องรอยว่าคิดมาได้ยังไง

ลำดับเหมือนของเดิมบน Magento: เรียงตาม priority แล้วกฎแรกที่เข้าเงื่อนไขและสั่งหยุดเป็นตัวชี้ขาด

  0  ส่งฟรีเมื่อยอดสุทธิ >= 6,000
  0  SB Care (มี SKU ในลิสต์) ส่งฟรี
  1  เรตเดียว 399 เมื่อยอด <= 5,999 และไม่มีสินค้าต้องห้ามอยู่ในตะกร้า
  3  ตารางน้ำหนัก แยกเขต — คิดจากน้ำหนักรวมเฉพาะสินค้าที่ flatpack_not_seller = 1

ต่างจากของเดิมสามข้อ ตั้งใจให้ต่าง:

  1. ไม่มี fallback เงียบๆ เป็น 199 — ของเดิมพอไม่มีกฎไหนเข้าจะคืน 199 ทุกครั้ง
     ซึ่งบนของจริงคือเกือบทุกครั้ง เพราะ mirror ขาด attribute ที่กฎใช้กรอง
     ของเราคืน needs_review แทน ให้หน้าเว็บบอกลูกค้าว่ารอเจ้าหน้าที่ประเมิน
  2. คิดจาก "รายการที่ติ๊กและต้องจัดส่ง" เท่านั้น ของยกกลับหน้าร้านไม่นับน้ำหนัก
  3. ยอดที่เอามาเทียบ 6,000 / 5,999 คือยอดสุทธิหลังหักส่วนลดแล้ว (package_value_with_discount)
"""

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cart import Cart, CartItem
from app.models.catalog import Material
from app.models.shipping import ShipArea, ShipAreaPostcode, ShipProductAttr, ShipRate, ShipRule

SHIP_MODES = ("ship", "install")


@dataclass
class ShipQuote:
    fee: Decimal = Decimal(0)
    area_id: int | None = None
    area_name: str | None = None
    source: str = "none"  # code ของกฎที่ชี้ขาด | "no_ship" | "none"
    weight_kg: Decimal = Decimal(0)
    needs_review: bool = False  # คิดอัตโนมัติไม่ครบ ต้องให้คนดู
    trace: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def has_rules(db: Session) -> bool:
    """ยังไม่ได้ ETL เข้ามา → ให้ผู้เรียกถอยไปใช้ค่าส่งจาก SAP ตามเดิม"""
    return db.scalar(select(ShipRule.id).where(ShipRule.is_active.is_(True)).limit(1)) is not None


def area_for_postcode(db: Session, postcode: str | None) -> ShipArea | None:
    """จับ prefix ยาวสุดก่อน (10270 ชนะ 102 ชนะ 10) แล้วค่อยตกไปที่เขตปริยาย"""
    pc = (postcode or "").strip()
    for n in (5, 4, 3, 2, 1):
        if len(pc) < n:
            continue
        row = db.get(ShipAreaPostcode, pc[:n])
        if row:
            return db.get(ShipArea, row.area_id)
    return db.scalar(select(ShipArea).where(ShipArea.is_default.is_(True)))


def _attrs_for(db: Session, skus: list[str]) -> dict[str, ShipProductAttr]:
    if not skus:
        return {}
    rows = db.scalars(select(ShipProductAttr).where(ShipProductAttr.sku.in_(skus))).all()
    return {r.sku: r for r in rows}


def _weight_of(db: Session, item: CartItem, attr: ShipProductAttr | None) -> Decimal | None:
    """น้ำหนักต่อชิ้น — เอาจากตารางค่าส่งก่อน ไม่มีค่อยถอยไปดูน้ำหนักในแคตตาล็อก"""
    if attr is not None and attr.weight_kg is not None:
        return Decimal(attr.weight_kg)
    m = db.get(Material, item.matnr)
    if m is not None and m.weight_kg is not None:
        return Decimal(m.weight_kg)
    return None


def _rate_for(db: Session, area_id: int, weight: Decimal) -> ShipRate | None:
    """ช่วงเป็นครึ่งเปิด [from, to) — น้ำหนักที่ตกขอบพอดีจึงมีเจ้าของแถวเดียวเสมอ"""
    return db.scalar(
        select(ShipRate)
        .where(ShipRate.area_id == area_id, ShipRate.weight_from <= weight, ShipRate.weight_to > weight)
        .order_by(ShipRate.weight_from.desc())
    )


def _match(rule: ShipRule, items: list[CartItem], attrs: dict[str, ShipProductAttr], net_total: Decimal) -> tuple[bool, str]:
    c = rule.conditions or {}
    if "min_subtotal" in c and net_total < Decimal(str(c["min_subtotal"])):
        return False, f"ยอดสุทธิ {net_total:,.2f} < {c['min_subtotal']:,}"
    if "max_subtotal" in c and net_total > Decimal(str(c["max_subtotal"])):
        return False, f"ยอดสุทธิ {net_total:,.2f} > {c['max_subtotal']:,}"
    if "any_sku" in c:
        want = {str(s).strip().upper() for s in c["any_sku"]}
        if not any((it.sku or "").strip().upper() in want for it in items):
            return False, "ไม่มี SKU ที่กำหนดในตะกร้า"
    clauses = c.get("require_item_all_of") or []
    if clauses:
        # ต้นทางใช้ Product\Found value=1 aggregator=all = "มีอย่างน้อย 1 รายการที่ผ่านครบทุกข้อ"
        # ไม่ใช่ "ทุกรายการต้องผ่าน" — ตะกร้าที่ปนของธรรมดากับของแฟลตแพ็คจึงเข้ากฎเรตเดียว
        if not any(_item_matches(it, attrs.get(it.sku), clauses) for it in items):
            return False, "ไม่มีรายการที่เข้าเงื่อนไขสินค้าของกฎนี้"
    return True, "เข้าเงื่อนไข"


def _item_matches(item: CartItem, attr: ShipProductAttr | None, clauses: list[dict]) -> bool:
    for cl in clauses:
        name, op, want = cl.get("attr"), cl.get("op"), str(cl.get("value", ""))
        if name == "name":
            has = want.lower() in (item.name_snapshot or "").lower()
            if (op == "contains" and not has) or (op == "!contains" and has):
                return False
            continue
        cur = "1" if getattr(attr, name, False) else "0"
        if (op == "==" and cur != want) or (op == "!=" and cur == want):
            return False
    return True


def quote(db: Session, cart: Cart, postcode: str | None, net_total: Decimal) -> ShipQuote:
    """คืนค่าส่งของทั้งตะกร้า + trace ทุกกฎที่ไล่ผ่าน (ใช้โชว์ให้เซลล์ตรวจได้)"""
    items = [it for it in cart.selected_items if it.supply_mode in SHIP_MODES]
    if not items:
        return ShipQuote(source="no_ship", trace=[{"rule": "-", "matched": False, "reason": "ไม่มีรายการที่ต้องจัดส่ง"}])

    area = area_for_postcode(db, postcode)
    attrs = _attrs_for(db, [it.sku for it in items])
    out = ShipQuote(area_id=area.id if area else None, area_name=area.name if area else None)

    rules = db.scalars(
        select(ShipRule).where(ShipRule.is_active.is_(True)).order_by(ShipRule.priority, ShipRule.code)
    ).all()

    matched = False
    for rule in rules:
        ok, reason = _match(rule, items, attrs, net_total)
        step = {"rule": rule.code, "name": rule.name, "priority": rule.priority, "matched": ok, "reason": reason}
        if not ok:
            out.trace.append(step)
            continue
        if rule.kind == "free":
            out.fee, out.source, matched = Decimal(0), rule.code, True
        elif rule.kind == "flat":
            out.fee, out.source, matched = Decimal(rule.fee), rule.code, True
        elif rule.kind == "table":
            fee, weight, status, detail = _table_fee(db, rule, items, attrs, area)
            step["weight_kg"] = f"{weight:.3f}"
            out.weight_kg = weight
            if status != "ok":
                step["matched"] = False
                step["reason"] = detail
                # ไม่มีสินค้าในขอบเขตของตาราง = กฎนี้ไม่เกี่ยว ไม่ใช่ความผิดพลาด ปล่อยให้กฎถัดไปทำงาน
                if status != "no_scope":
                    out.needs_review = True
                    out.warnings.append(detail)
                out.trace.append(step)
                continue
            out.fee, out.source, matched, step["reason"] = fee, rule.code, True, detail
        out.trace.append(step)
        if rule.stop_on_match:
            break

    if not matched and not out.needs_review:
        out.needs_review = True
        out.warnings.append("ไม่มีกฎค่าส่งข้อใดตรงกับตะกร้านี้ — รอเจ้าหน้าที่ประเมิน")
    return out


def _table_fee(
    db: Session, rule: ShipRule, items: list[CartItem], attrs: dict[str, ShipProductAttr], area: ShipArea | None,
) -> tuple[Decimal | None, Decimal, str, str]:
    """น้ำหนักรวม = ผลรวม (น้ำหนักต่อชิ้น × จำนวน) เฉพาะสินค้าที่ติดธงตามที่กฎกำหนด

    คืน (ค่าส่ง, น้ำหนักรวม, สถานะ, คำอธิบาย) — สถานะ no_scope แปลว่ากฎนี้ไม่เกี่ยวกับตะกร้านี้
    ส่วน unknown_weight / out_of_range / no_area คือคิดไม่ได้จริง ต้องให้คนดู
    """
    flag = (rule.conditions or {}).get("weight_attr")
    scope = [it for it in items if not flag or getattr(attrs.get(it.sku), flag, False)]
    total = Decimal(0)
    unknown: list[str] = []
    for it in scope:
        w = _weight_of(db, it, attrs.get(it.sku))
        if w is None:
            unknown.append(it.sku)
            continue
        total += w * it.qty
    if not scope:
        return None, total, "no_scope", f"ไม่มีสินค้าที่ {flag}=1 ในตะกร้า" if flag else "ไม่มีสินค้าที่ต้องจัดส่ง"
    if unknown:
        return None, total, "unknown_weight", f"ยังไม่มีน้ำหนักของ {len(unknown)} รายการ ({', '.join(unknown[:3])}) — ค่าส่งรอเจ้าหน้าที่ประเมิน"
    if area is None:
        return None, total, "no_area", "ไม่รู้เขตจัดส่งจากรหัสไปรษณีย์นี้ — ค่าส่งรอเจ้าหน้าที่ประเมิน"
    rate = _rate_for(db, area.id, total)
    if rate is None:
        return None, total, "out_of_range", f"น้ำหนักรวม {total:,.2f} kg อยู่นอกตารางค่าส่งของ{area.name} — รอเจ้าหน้าที่ประเมิน"
    return Decimal(rate.fee), total, "ok", f"น้ำหนักรวม {total:,.2f} kg · {area.name} · {Decimal(rate.fee):,.2f} บาท"
