"""เช็คสต็อกกับ SAP ทั้งตะกร้าครั้งเดียว แล้วแปลตัวเลข ATP เป็นคำที่เซลล์อ่านรู้เรื่อง

ไม่แตะ stock_checks/stock_cache เดิม เพราะสองตัวนั้นผูกกับ plant (สาขา) ส่วน API นี้ไม่บอกสาขา
เลย — เก็บร่องรอยไว้ใน audit_logs แทน
"""
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.sap.availability import AvailAsk, AvailLine, get_availability_client
from app.integrations.sap.base import SapError
from app.models.cart import Cart
from app.models.catalog import Material
from app.models.common import utcnow
from app.models.user import User
from app.services import audit_service

log = logging.getLogger("sb.availability")

# full  = ได้ครบตามวันที่ขอ
# split = ได้ครบ แต่ต้องแบ่งส่ง มีบางส่วนรอถึงวันหลัง
# short = ยืนยันได้บางส่วน ที่เหลือ SAP ยังไม่ให้วัน
# none  = ไม่มีของเลย
# unknown = SAP ไม่รู้จักรหัสนี้
STATUS_LABEL = {
    "full": "มีของ",
    "split": "ได้ครบ แต่แบ่งส่ง",
    "short": "ของไม่พอ",
    "none": "ไม่มีของ",
    "unknown": "SAP ไม่รู้จักรหัสนี้",
}


@dataclass
class ItemAvailability:
    item_id: str | None
    matnr: str
    name: str
    qty: int
    status: str
    label: str
    ready_qty: int  # ได้ทันทีตามวันที่ขอ
    ready_date: date | None
    later_qty: int  # ต้องรอถึง later_date
    later_date: date | None
    short_qty: int  # ยังหาไม่ได้
    sap_name: str | None = None
    sap_unit_price: Decimal | None = None  # ราคาป้ายฝั่ง SAP (ก่อนลด)
    sap_amount: Decimal | None = None  # ยอดสุทธิของบรรทัดนี้จาก SAP
    sap_discount_percent: float | None = None
    our_amount: Decimal | None = None  # ยอดที่เราเก็บ snapshot ไว้ในตะกร้า
    price_diff: Decimal | None = None  # SAP − เรา (บวก = SAP แพงกว่า)


@dataclass
class CartAvailability:
    cart_id: str | None
    checked_at: datetime
    req_date: date
    customer_no: str
    is_walkin: bool
    source: str  # sap | mock
    items: list[ItemAvailability]
    all_ok: bool
    message: str


def req_date_for(today: date | None = None) -> date:
    return (today or utcnow().date()) + timedelta(days=get_settings().sap_avail_lead_days)


def _classify(ask_qty: int, line: AvailLine | None, matnr: str, name: str, our_unit_price: Decimal | None, item_id: str | None = None) -> ItemAvailability:
    if line is None:
        return ItemAvailability(
            item_id=item_id, matnr=matnr, name=name, qty=ask_qty, status="unknown", label=STATUS_LABEL["unknown"],
            ready_qty=0, ready_date=None, later_qty=0, later_date=None, short_qty=ask_qty,
        )
    # available = ของที่มีตอนนี้ (ทั้งก้อน) — ตัดที่ ask_qty ถึงจะเป็นจำนวนที่บรรทัดนี้ได้จริง
    ready = max(0, min(line.available_qty, ask_qty))
    later = max(0, line.committed_qty)
    if ready + later > ask_qty:
        later = max(0, ask_qty - ready)
    short = max(0, ask_qty - ready - later)
    if ready >= ask_qty:
        status = "full"
    elif short == 0:
        status = "split"
    elif ready + later > 0:
        status = "short"
    else:
        status = "none"
    our = (Decimal(our_unit_price) * ask_qty) if our_unit_price is not None else None
    return ItemAvailability(
        item_id=item_id, matnr=matnr, name=name, qty=ask_qty, status=status, label=STATUS_LABEL[status],
        ready_qty=ready, ready_date=line.available_date if ready else None,
        later_qty=later, later_date=line.committed_date if later else None, short_qty=short,
        sap_name=line.description, sap_unit_price=line.unit_price or None, sap_amount=line.amount or None,
        sap_discount_percent=line.discount_percent or None, our_amount=our,
        price_diff=(line.amount - our) if (our is not None and line.amount) else None,
    )


def _summarize(items: list[ItemAvailability]) -> tuple[bool, str]:
    bad = [o for o in items if o.status not in ("full", "split")]
    if not items:
        return False, "ตะกร้ายังไม่มีสินค้า"
    if bad:
        return False, f"มี {len(bad)} รายการที่ของไม่พอ — คุยกับลูกค้าก่อนออกใบเสนอราคา"
    return True, "ของครบทุกรายการ" if all(o.status == "full" for o in items) else "ของครบ แต่บางรายการต้องแบ่งส่ง"


def check_cart(db: Session, cart: Cart, actor: User | None) -> CartAvailability:
    """ยิงทั้งตะกร้าครั้งเดียว — ยิงทีละชิ้นจะเห็นของซ้ำแล้วขายเกิน"""
    s = get_settings()
    items = [it for it in cart.items if it.qty > 0]
    customer_no = (cart.customer.sap_customer_no if cart.customer else None) or s.sap_walkin_customer
    req = req_date_for()
    asks = [AvailAsk(matnr=it.matnr, qty=it.qty) for it in items]
    client = get_availability_client()
    source = "mock" if type(client).__name__.startswith("Mock") else "sap"
    lines = client.check(asks, customer_no, req) if asks else []
    out = [_classify(it.qty, ln, it.matnr, it.name_snapshot, it.unit_price_snapshot, it.id) for it, ln in zip(items, lines)]
    all_ok, message = _summarize(out)
    bad = [o for o in out if o.status not in ("full", "split")]
    audit_service.log(db, actor, "sap.availability", "cart", cart.id, {
        "customer": customer_no, "req_date": req.isoformat(), "source": source,
        "lines": len(out), "not_ok": len(bad),
    })
    db.commit()
    return CartAvailability(
        cart_id=cart.id, checked_at=utcnow(), req_date=req, customer_no=customer_no,
        is_walkin=customer_no == s.sap_walkin_customer, source=source, items=out, all_ok=all_ok, message=message,
    )


def check_lines(db: Session, lines_in: list[tuple[str, int]], actor: User | None, customer_no: str | None = None) -> CartAvailability:
    """เช็คสต็อกรายการชุดหนึ่งโดยไม่ต้องมีตะกร้า — ยังยิง SAP ครั้งเดียวทั้งชุดเหมือนเดิม

    มีไว้ให้ช่องทางที่ไม่ได้เปิดตะกร้าไว้ (เช่น MCP ที่ให้ Claude ถามแทนเซลล์) เรียกใช้
    ห้ามทำเป็น loop เรียก check_one ทีละตัว เพราะ SAP จำลองทั้งบิล ของชิ้นเดียวจะถูก
    นับซ้ำให้ทุกบรรทัด = ขายเกิน (ดู docstring ของ integrations/sap/availability.py)
    """
    s = get_settings()
    asks = [AvailAsk(matnr=m, qty=max(1, q)) for m, q in lines_in if m]
    cust = customer_no or s.sap_walkin_customer
    req = req_date_for()
    client = get_availability_client()
    source = "mock" if type(client).__name__.startswith("Mock") else "sap"
    got = client.check(asks, cust, req) if asks else []
    names = {m.matnr: m.name_th for m in db.scalars(select(Material).where(Material.matnr.in_([a.matnr for a in asks]))).all()} if asks else {}
    out = [_classify(a.qty, ln, a.matnr, names.get(a.matnr, a.matnr), None) for a, ln in zip(asks, got)]
    all_ok, message = _summarize(out)
    audit_service.log(db, actor, "sap.availability", "lines", None, {
        "customer": cust, "req_date": req.isoformat(), "source": source,
        "lines": len(out), "not_ok": len([o for o in out if o.status not in ("full", "split")]),
    })
    db.commit()
    return CartAvailability(
        cart_id=None, checked_at=utcnow(), req_date=req, customer_no=cust,
        is_walkin=cust == s.sap_walkin_customer, source=source, items=out, all_ok=all_ok, message=message,
    )


def check_one(db: Session, matnr: str, qty: int, name: str, actor: User | None, customer_no: str | None = None) -> ItemAvailability:
    """เช็คสินค้าตัวเดียว (ตอนค้นหาก่อนใส่ตะกร้า) — ตะกร้ายังไม่มีของ ยิงเดี่ยวไม่มีปัญหาของซ้ำ"""
    s = get_settings()
    cust = customer_no or s.sap_walkin_customer
    req = req_date_for()
    lines = get_availability_client().check([AvailAsk(matnr=matnr, qty=max(1, qty))], cust, req)
    res = _classify(max(1, qty), lines[0] if lines else None, matnr, name, None)
    audit_service.log(db, actor, "sap.availability", "material", matnr, {"customer": cust, "qty": qty, "status": res.status})
    db.commit()
    return res


__all__ = ["CartAvailability", "ItemAvailability", "SapError", "check_cart", "check_lines", "check_one", "req_date_for"]
