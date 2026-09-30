"""กติกาโปรโมชั่นแบบ rule-based สำหรับ mock (ของจริง SAP/ทีมหลังบ้านคำนวณ — ดู BUILD_PROMPT ข้อ 7.1)
คืนทั้งโปรที่เข้าเงื่อนไข และที่ยังไม่เข้าเงื่อนไขพร้อมเหตุผลว่าขาดอะไร
"""
from datetime import date
from decimal import Decimal

from app.integrations.sap.base import CartDTO, CustomerDTO, PromoOffer, PromoResult

STAFF_QUOTA_PERCENT = 3.0


def _fmt(n: Decimal | float | int) -> str:
    return f"{Decimal(n):,.0f}"


def evaluate(promotions: list[dict], cart: CartDTO, customer: CustomerDTO | None, category_roots: dict[str, str], zone: str | None = None) -> PromoResult:
    today = date.today()
    eligible: list[PromoOffer] = []
    ineligible: list[PromoOffer] = []
    for p in promotions:
        vf, vt = p.get("valid_from"), p.get("valid_to")
        if (vf and today < date.fromisoformat(vf)) or (vt and today > date.fromisoformat(vt)):
            continue
        cond = p["condition"]
        kind = cond["type"]
        amount = Decimal(0)
        reason: str | None = None

        if kind == "category_percent":
            root = cond["category_root"]
            cat_sub = sum((l.unit_price * l.qty for l in cart.lines if category_roots.get(l.category_id or "", l.category_id) == root), Decimal(0))
            if cat_sub <= 0:
                reason = f"ยังไม่เข้าเงื่อนไข: ต้องมีสินค้าหมวด{_root_name(root)}ในบิล"
            elif cat_sub < cond["min_category_subtotal"]:
                reason = f"ยังไม่เข้าเงื่อนไข: ยอดหมวด{_root_name(root)}ขาดอีก {_fmt(Decimal(cond['min_category_subtotal']) - cat_sub)}.-"
            else:
                amount = (cat_sub * Decimal(cond["percent"]) / 100).quantize(Decimal("1"))

        elif kind == "free_shipping":
            if not customer:
                reason = "ยังไม่เข้าเงื่อนไข: ต้องผูกลูกค้าสมาชิกก่อน"
            elif cart.subtotal < cond["min_subtotal"]:
                reason = f"ยังไม่เข้าเงื่อนไข: ยอดขาดอีก {_fmt(Decimal(cond['min_subtotal']) - cart.subtotal)}.-"
            elif zone and zone not in cond.get("zones", [zone]):
                reason = "ยังไม่เข้าเงื่อนไข: ที่อยู่จัดส่งอยู่นอกเขต กทม."
            else:
                amount = Decimal(cond["max_amount"])

        elif kind in ("subtotal_amount", "subtotal_percent", "code_amount", "code_percent"):
            # คิดจากยอดบิลอย่างเดียว — ใช้ได้ทั้งโปรฯ ที่ระบบเช็คเอง และคูปองที่ต้องกรอกโค้ด
            # (ต่างกันที่ธง requires_code ไม่ใช่ที่สูตรคิดเงิน)
            need = Decimal(cond.get("min_subtotal", 0))
            if cart.subtotal < need:
                reason = f"ยังไม่เข้าเงื่อนไข: ยอดขาดอีก {_fmt(need - cart.subtotal)}.-"
            elif kind.endswith("_amount"):
                amount = Decimal(cond["amount"])
            else:
                cap = Decimal(cond.get("max_amount", 10**9))
                amount = min(cap, (cart.subtotal * Decimal(cond["percent"]) / 100).quantize(Decimal("1")))

        elif kind == "bundle_gift":
            root = cond["category_root"]
            qty = sum(l.qty for l in cart.lines if category_roots.get(l.category_id or "", l.category_id) == root)
            if qty < cond["min_qty"]:
                reason = f"ยังไม่เข้าเงื่อนไข: ต้องมี{_root_name(root)}ในบิล (ขาด {cond['min_qty'] - qty} ชิ้น)"
            else:
                amount = Decimal(cond["gift_value"])

        offer = PromoOffer(code=p["code"], title=p["title"], condition_text=p["condition_text"], eligible=reason is None, amount=amount, reason=reason, stackable=bool(p.get("stackable", True)), discount_type=p.get("discount_type", "amount"), requires_code=bool(p.get("requires_code", False)), exclusive_group=p.get("exclusive_group"))
        (eligible if offer.eligible else ineligible).append(offer)
    return PromoResult(eligible=eligible, ineligible=ineligible, staff_discount_quota_percent=STAFF_QUOTA_PERCENT)


def _root_name(root: str) -> str:
    return {"sofa": "โซฟา", "mattress": "ที่นอน", "bedroom": "ห้องนอน", "dining": "โต๊ะอาหาร"}.get(root, root)
