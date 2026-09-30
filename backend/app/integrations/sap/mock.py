"""MockSapClient — อ่านจาก seed/sap_mock/*.json (แมท 20 ตัว, สต็อก 4 สาขา, โปร 3 ตัว, โซนจัดส่ง 5 โซน)
ใช้ทั้งตอน dev และใน test · จำลอง SAP ล่มได้ด้วย fail_next(n)
"""
import json
import random
import string
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.integrations.sap.base import (
    CartDTO,
    CustomerDTO,
    DeliveryQuote,
    DeliverySlotDTO,
    MaterialDTO,
    OrderDTO,
    OrderLineDTO,
    PromoResult,
    SapError,
    SapSoResult,
    StockRow,
)
from app.integrations.sap.promo_engine import evaluate as evaluate_promo_rules

SEED_DIR = Path(__file__).resolve().parents[3] / "seed" / "sap_mock"


def _load(name: str):
    with open(SEED_DIR / name, encoding="utf-8") as f:
        return json.load(f)


class MockSapClient:
    def __init__(self, seed_dir: Path | None = None):
        self.seed_dir = seed_dir or SEED_DIR
        self._materials = [self._to_material(m) for m in _load("materials.json")]
        self._stock = _load("stock.json")
        self._plants = {p["plant_code"]: p for p in _load("plants.json")}
        self._promotions = _load("promotions.json")
        self._zones = _load("delivery_zones.json")
        self._customers = _load("customers.json")
        self._fail_calls = 0
        self.calls: list[tuple[str, tuple]] = []  # เก็บ log call ไว้ตรวจใน test
        self.created_orders: list[str] = []

    # ---------- test helpers ----------
    def fail_next(self, n: int = 1) -> None:
        """ให้ n call ถัดไปโยน SapError (จำลอง timeout/ล่ม)"""
        self._fail_calls = n

    def _maybe_fail(self, name: str, *args) -> None:
        self.calls.append((name, args))
        if self._fail_calls > 0:
            self._fail_calls -= 1
            raise SapError(f"SAP mock: simulated outage on {name}")

    # ---------- mapping ----------
    @staticmethod
    def _to_material(m: dict) -> MaterialDTO:
        price = float(m["price"])
        prices = {"standard": price}
        if m.get("compare_at"):
            prices["compare_at"] = float(m["compare_at"])
        return MaterialDTO(
            matnr=m["matnr"], sku=m["sku"], barcode=m.get("barcode"), name_th=m["name_th"], name_en=m.get("name_en"),
            variant=m.get("variant"), spec=m.get("spec"), description=m.get("description"), category_id=m.get("category_id"),
            brand_id=m.get("brand_id"), room=m.get("room"), image_url=m.get("image_url"), requires_install=bool(m.get("requires_install")),
            is_takeaway_ok=bool(m.get("is_takeaway_ok", True)), is_new=bool(m.get("is_new")), volume_m3=m.get("volume_m3"),
            weight_kg=m.get("weight_kg"), tags=list(m.get("tags") or []), prices=prices,
        )

    # ---------- SapClient ----------
    def list_materials(self) -> list[MaterialDTO]:
        self._maybe_fail("list_materials")
        return list(self._materials)

    def search_materials(self, q: str, limit: int = 20) -> list[MaterialDTO]:
        self._maybe_fail("search_materials", q)
        ql = (q or "").strip().lower()
        out = [m for m in self._materials if not ql or ql in m.name_th.lower() or ql in (m.name_en or "").lower() or ql in m.matnr or ql in m.sku.lower() or ql == (m.barcode or "")]
        return out[:limit]

    def get_stock(self, matnr: str) -> list[StockRow]:
        self._maybe_fail("get_stock", matnr)
        rows = self._stock.get(matnr)
        if rows is None:
            raise SapError(f"SAP mock: unknown MATNR {matnr}")
        today = date.today()
        out: list[StockRow] = []
        for code, s in rows.items():
            plant = self._plants[code]
            atp = today + timedelta(days=s["atp_days"]) if s.get("atp_days") is not None else None
            note = s.get("note")
            if s["on_hand"] - s.get("reserved", 0) <= 0 and s.get("next_in_days"):
                note = f"ของหมด · ของเข้ารอบถัดไป {(today + timedelta(days=s['next_in_days'])).strftime('%d/%m')}"
            out.append(StockRow(matnr=matnr, plant_code=code, plant_name=plant["name"], plant_type=plant["type"], on_hand=s["on_hand"], reserved=s.get("reserved", 0), atp_date=atp, note=note))
        return out

    def evaluate_promotions(self, cart: CartDTO, customer: CustomerDTO | None) -> PromoResult:
        self._maybe_fail("evaluate_promotions", cart.cart_id)
        return evaluate_promo_rules(self._promotions, cart, customer, category_roots=self._category_roots())

    def _category_roots(self) -> dict[str, str]:
        roots: dict[str, str] = {}
        for c in _load("categories.json"):
            roots[c["id"]] = c["id"]
            for ch in c.get("children", []):
                roots[ch["id"]] = c["id"]
        return roots

    def zone_for(self, postcode: str) -> str | None:
        pc = (postcode or "").strip()
        if pc in self._zones["postcodes"]:
            return self._zones["postcodes"][pc]
        for rule in self._zones["prefix_rules"]:
            if pc.startswith(rule["prefix"]):
                return rule["zone"]
        return None

    def quote_delivery(self, cart: CartDTO, postcode: str) -> DeliveryQuote:
        self._maybe_fail("quote_delivery", cart.cart_id, postcode)
        zone = self.zone_for(postcode)
        if not zone:
            raise SapError(f"SAP mock: ไม่รู้จักรหัสไปรษณีย์ {postcode}")
        z = self._zones["zones"][zone]
        groups: dict[str, list[str]] = {"takeaway": [], "ship": [], "install": []}
        for line in cart.lines:
            mode = line.supply_mode if line.supply_mode in groups else "ship"
            if line.requires_install and mode != "takeaway":
                mode = "install"
            groups[mode].append(line.matnr)
        base = Decimal(z["base_fee"]) if (groups["ship"] or groups["install"]) else Decimal(0)
        install = Decimal(z["install_fee"]) if groups["install"] else Decimal(0)
        slots: list[DeliverySlotDTO] = []
        start = date.today() + timedelta(days=z["lead_days"])
        quota = self._zones["slot_quota_per_period"][zone]
        for i in range(7):
            d = start + timedelta(days=i)
            for period in ("am", "pm"):
                booked = quota if (i == 0 and period == "pm") else (i * 2 + (1 if period == "pm" else 0)) % max(1, quota - 1)
                slots.append(DeliverySlotDTO(id=f"{zone}-{d.isoformat()}-{period}", date=d, period=period, zone=zone, quota=quota, booked=booked))
        return DeliveryQuote(postcode=postcode, zone=zone, zone_name=z["name"], base_fee=base, install_fee=install, total_fee=base + install, groups=groups, slots=slots)

    def create_sales_order(self, quotation_no: str) -> SapSoResult:
        self._maybe_fail("create_sales_order", quotation_no)
        so = "26" + "".join(random.choices(string.digits, k=8))
        self.created_orders.append(so)
        return SapSoResult(ok=True, sap_so_no=so, message="mock SO created")

    def create_sales_order_doc(self, order) -> SapSoResult:
        """mock: เก็บ payload ล่าสุดไว้ให้เทสตรวจว่าเราส่งอะไรออกไป"""
        self.last_so_payload = order.to_payload()
        return self.create_sales_order(order.quotation_no)

    def get_order_history(self, sap_customer_no: str) -> list[OrderDTO]:
        """mock: สุ่มแบบ deterministic จากเลขลูกค้า — ลูกค้าคนเดิมได้ประวัติเดิมทุกครั้ง"""
        self._maybe_fail("get_order_history", sap_customer_no)
        rnd = random.Random(sap_customer_no)
        today = date.today()
        orders: list[OrderDTO] = []
        for i in range(rnd.randint(2, 5)):
            ordered = today - timedelta(days=rnd.randint(20, 700))
            picks = rnd.sample(self._materials, rnd.randint(1, 3))
            lines = []
            for m in picks:
                qty = rnd.randint(1, 2)
                unit = Decimal(str(m.prices.get("standard", 0)))
                lines.append(OrderLineDTO(matnr=m.matnr, name=m.name_th, qty=qty, unit_price=unit, line_total=unit * qty))
            total = sum((l.line_total for l in lines), Decimal(0))
            age = (today - ordered).days
            status = "delivered" if age > 30 else rnd.choice(["shipping", "in_production", "confirmed"])
            orders.append(OrderDTO(
                so_no="26" + str(abs(hash((sap_customer_no, i))) % 10**8).zfill(8), sap_customer_no=sap_customer_no, order_date=ordered, status=status,
                grand_total=total, channel=rnd.choice(["online", "in_store_assisted"]), branch=rnd.choice(["SB Design Square บางนา", "SB Design Square เซ็นทรัลเวิลด์", "SB Design Square รัชดา"]),
                delivery_date=ordered + timedelta(days=rnd.randint(3, 21)), lines=lines,
            ))
        return sorted(orders, key=lambda o: o.order_date, reverse=True)

    def get_customer(self, key: str) -> CustomerDTO | None:
        self._maybe_fail("get_customer", key)
        k = (key or "").strip().lower()
        digits = "".join(ch for ch in k if ch.isdigit())
        for c in self._customers:
            if k in (c["sap_customer_no"], c["email"].lower()) or (digits and digits == c["phone"]):
                return CustomerDTO(**c)
        return None
