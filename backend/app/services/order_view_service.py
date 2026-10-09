"""ประวัติคำสั่งซื้อของลูกค้า (หน้า "ประวัติการสั่งซื้อ") — รวมสองแหล่งเป็นรายการเดียว

  1. คำสั่งซื้อที่จ่ายผ่านเว็บเรา (ใบที่ชำระแล้ว) — รู้ละเอียด: สั่งเมื่อ ชำระเมื่อ ช่องทาง ที่อยู่ส่ง
  2. ประวัติจาก SAP (order_history ที่ sync มา) — ของที่ซื้อหน้าร้านก่อนมีเว็บ รู้แค่วันสั่ง/สถานะ/วันส่ง

ใบเว็บที่ SAP ก็มีแล้ว (เลข SO ตรงกัน) แสดงครั้งเดียว ใช้รายละเอียดจากเว็บ + สถานะล่าสุดจาก SAP

ไทม์ไลน์สถานะแบบ Shopee: สั่งซื้อ → ชำระเงิน → ยืนยันคำสั่งซื้อ → เตรียมสินค้า → กำลังจัดส่ง → ส่งสำเร็จ
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.analytics import OrderHistory
from app.models.catalog import Material
from app.models.payment import Payment
from app.models.quotation import Quotation
from app.models.user import User
from app.services import analytics_service

STATUS_TXT = {
    "paid": "ชำระแล้ว · รอยืนยัน", "confirmed": "ยืนยันแล้ว", "in_production": "กำลังเตรียมสินค้า",
    "shipping": "กำลังจัดส่ง", "delivered": "ส่งสำเร็จ", "cancelled": "ยกเลิก",
}
METHOD_TXT = {"qr_promptpay": "QR PromptPay", "card": "บัตรเครดิต/เดบิต", "installment": "ผ่อน 0%", "link": "ลิงก์ชำระเงิน"}
SUPPLY_TXT = {"takeaway": "ยกกลับ", "ship": "จัดส่ง", "install": "ส่ง+ติดตั้ง", "pickup": "รับที่สาขา"}
STEPS = [("ordered", "สั่งซื้อ"), ("paid", "ชำระเงิน"), ("confirmed", "ยืนยันคำสั่งซื้อ"),
         ("in_production", "เตรียมสินค้า"), ("shipping", "กำลังจัดส่ง"), ("delivered", "ส่งสำเร็จ")]
_RANK = {k: i for i, (k, _) in enumerate(STEPS)}


def _materials(db: Session, matnrs: list[str]) -> dict[str, Material]:
    if not matnrs:
        return {}
    return {m.matnr: m for m in db.scalars(select(Material).where(Material.matnr.in_(set(matnrs)))).all()}


def _line(m: Material | None, matnr: str, name: str, qty: int, unit, total, variant=None, supply=None, remark=None) -> dict:
    return {
        "matnr": matnr, "name": name, "variant": variant, "qty": qty,
        "unit_price": Decimal(unit), "line_total": Decimal(total),
        "image_url": (m.image_url if m and m.image_url else None),
        "linkable": m is not None,          # มีหน้าสินค้าในเว็บ → กดเข้าไปดูได้
        "supply": SUPPLY_TXT.get(supply or "", None), "remark": remark,
    }


def _steps(status: str, ordered_at, paid_at, delivered_on, paid_label: str) -> list[dict]:
    if status == "cancelled":
        return [{"key": "ordered", "label": "สั่งซื้อ", "done": True, "at": ordered_at},
                {"key": "cancelled", "label": "ยกเลิก", "done": True, "at": None}]
    cur = _RANK.get(status, _RANK["confirmed"])
    at = {"ordered": ordered_at, "paid": paid_at, "delivered": delivered_on if status == "delivered" else None}
    return [{"key": k, "label": paid_label if k == "paid" else label, "done": i <= cur, "at": at.get(k)}
            for i, (k, label) in enumerate(STEPS)]


def _from_web(db: Session, q: Quotation, sap: OrderHistory | None, mats: dict) -> dict:
    from app.services import staff_shipping_service

    charges = staff_shipping_service.charge_matnrs()
    pay = db.scalar(select(Payment).where(Payment.quotation_id == q.id, Payment.status == "paid")
                    .order_by(Payment.paid_at.desc()))
    # สถานะ: SAP รู้ล่าสุด (ผลิต/ส่ง) ถ้ามีเลข SO แล้ว · ยังไม่มี SO = จ่ายแล้วรอยืนยัน
    status = sap.status if sap else ("confirmed" if q.status == "converted" else "paid")
    c = q.customer_snapshot or {}
    fee = Decimal(q.shipping_fee) + Decimal(q.install_fee) - Decimal(q.shipping_discount)
    return {
        "key": q.sap_so_no or q.quotation_no,
        "so_no": q.sap_so_no or q.quotation_no, "order_no": q.sap_so_no, "quotation_no": q.quotation_no,
        "source": "web", "channel": q.channel,
        "status": status, "status_text": STATUS_TXT.get(status, status),
        "order_date": q.issued_at.date(), "ordered_at": q.issued_at, "paid_at": q.paid_at,
        "payment_method": METHOD_TXT.get(pay.method, pay.method) if pay else None,
        "branch": q.sales.branch_name if q.sales else None,
        "sales_name": q.sales.name if q.sales else None,
        "receiver": c.get("name"), "phone": c.get("phone"),
        "ship_address": " ".join(x for x in [q.ship_address or "", q.ship_postcode or ""] if x) or None,
        "delivery_date": (sap.delivery_date if sap and sap.delivery_date else q.slot_date),
        "subtotal": Decimal(q.subtotal), "discount_total": Decimal(q.discount_total), "shipping_fee": fee,
        "vat": Decimal(q.vat), "grand_total": Decimal(q.grand_total),
        "lines": [_line(mats.get(l.matnr), l.matnr, l.name, l.qty, l.unit_price, l.line_total, l.variant, l.supply_mode, l.item_remark)
                  for l in sorted(q.lines, key=lambda x: x.sort) if l.matnr not in charges],
        "steps": _steps(status, q.issued_at, q.paid_at, sap.delivery_date if sap else None, "ชำระเงิน"),
        "synced_at": sap.synced_at if sap else q.paid_at,
    }


def _from_sap(o: OrderHistory, mats: dict) -> dict:
    # ซื้อหน้าร้านผ่าน SAP: จ่ายที่สาขา ไม่มีเวลาจ่าย/ที่อยู่ในประวัติ — บอกเท่าที่รู้จริง
    total = sum((Decimal(l.line_total) for l in o.lines), Decimal(0))
    return {
        "key": o.so_no, "so_no": o.so_no, "order_no": o.so_no, "quotation_no": None,
        "source": "sap", "channel": o.channel,
        "status": o.status, "status_text": STATUS_TXT.get(o.status, o.status),
        "order_date": o.order_date, "ordered_at": None, "paid_at": None,
        "payment_method": "ชำระที่สาขา" if o.channel != "online" else None,
        "branch": o.branch, "sales_name": None, "receiver": None, "phone": None, "ship_address": None,
        "delivery_date": o.delivery_date,
        "subtotal": total, "discount_total": Decimal(0), "shipping_fee": Decimal(o.grand_total) - total if Decimal(o.grand_total) > total else Decimal(0),
        "vat": None, "grand_total": Decimal(o.grand_total),
        "lines": [_line(mats.get(l.matnr), l.matnr, l.name, l.qty, l.unit_price, l.line_total) for l in o.lines],
        "steps": _steps(o.status, o.order_date, o.order_date, o.delivery_date,
                        "ชำระที่สาขา" if o.channel != "online" else "ชำระเงิน"),
        "synced_at": o.synced_at,
    }


def list_views(db: Session, user: User) -> list[dict]:
    sap_rows = analytics_service.list_orders(db, user)          # sync จาก SAP ในตัว
    by_so = {o.so_no: o for o in sap_rows}
    web = db.scalars(
        select(Quotation).options(selectinload(Quotation.lines), selectinload(Quotation.sales))
        .where(Quotation.customer_user_id == user.id, Quotation.status.in_(("paid", "converted")))
    ).all()
    mats = _materials(db, [l.matnr for q in web for l in q.lines] + [l.matnr for o in sap_rows for l in o.lines])
    out = [_from_web(db, q, by_so.get(q.sap_so_no or ""), mats) for q in web]
    used = {q.sap_so_no for q in web if q.sap_so_no}
    out += [_from_sap(o, mats) for o in sap_rows if o.so_no not in used]

    def sort_key(v):
        d = v["ordered_at"] or datetime.combine(v["order_date"], datetime.min.time())
        return d
    return sorted(out, key=sort_key, reverse=True)


def get_view(db: Session, user: User, key: str) -> dict | None:
    v = next((v for v in list_views(db, user) if key in (v["key"], v["so_no"], v["quotation_no"])), None)
    if v or not user.is_staff:
        return v
    # พนักงานเปิดดูออร์เดอร์ของลูกค้าได้ (เหมือนเดิม) — ใช้ข้อมูลจาก SAP mirror
    o = analytics_service.get_order(db, user, key)
    return _from_sap(o, _materials(db, [l.matnr for l in o.lines])) if o else None
