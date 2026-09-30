"""ส่งใบเสนอราคาที่จ่ายเงินแล้วไปสร้าง Sales Order ที่ SAP แล้วรับเลข SO กลับมา

ขอบเขตของฝั่งเรามีแค่นี้: **ส่งไป แล้วรับเลข SO กลับ** — SAP เป็นคนสร้างเอกสารจริง
เราไม่คำนวณอะไรใหม่ ไม่แก้ราคา ส่งสิ่งที่ลูกค้าจ่ายเงินไปแล้วตามนั้นเป๊ะ

payload สร้างจาก Quotation ที่ commit ไปแล้ว (ดู build_sales_order) — ไม่ใช่ดึงสดจาก
ตะกร้าหรือ SAP ใหม่ เพราะราคา/ส่วนลด/ค่าส่ง ต้องเป็นชุดเดียวกับที่ลูกค้าเห็นและจ่าย
ไม่งั้นยอดในใบเสร็จกับใน SAP จะไม่ตรงกันเมื่อโปรโมชันหมดอายุระหว่างทาง

รูปแบบ JSON ที่ตกลงกับฝั่งหลังบ้าน: docs/sap-sales-order.md
"""
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class SoLine:
    """หนึ่งบรรทัดสินค้า — line_no เป็น 10, 20, 30... ตามธรรมเนียม POSNR ของ SAP"""

    line_no: int
    matnr: str
    name: str
    qty: int
    unit_price: Decimal
    line_discount: Decimal
    line_total: Decimal
    supply_mode: str            # takeaway | ship | install | pickup
    plant_code: str | None
    atp_date: date | None
    requires_install: bool


@dataclass
class SoAmounts:
    subtotal: Decimal
    discount_total: Decimal
    shipping_fee: Decimal
    install_fee: Decimal
    shipping_discount: Decimal
    vat: Decimal                # VAT 7% ที่รวมอยู่ในยอดแล้ว ไม่ใช่บวกเพิ่ม
    grand_total: Decimal
    deposit_amount: Decimal


@dataclass
class SalesOrderDTO:
    """ทุกอย่างที่ SAP ต้องใช้สร้าง SO หนึ่งใบ — ไม่ต้องย้อนมาถามเราอีก"""

    quotation_no: str
    customer_no: str            # CUST · ลูกค้าที่ไม่ได้เป็นสมาชิกใช้เลข walk-in จาก config
    order_type: str
    sales_org: str
    distr_chan: str
    division: str
    req_date: date              # วันที่ลูกค้าต้องการของ
    channel: str                # online | in_store_assisted
    customer_name: str
    customer_phone: str | None
    customer_email: str | None
    ship_address: str | None
    ship_postcode: str | None
    ship_zone: str | None
    slot_date: date | None
    slot_period: str | None     # am | pm
    amounts: SoAmounts
    items: list[SoLine] = field(default_factory=list)
    payment_no: str | None = None
    paid_at: str | None = None

    def to_payload(self) -> dict:
        """แปลงเป็น dict พร้อมส่ง — Decimal/date เป็น string เพื่อไม่ให้ปัดเศษเพี้ยนระหว่างทาง

        ตัวเลขเงินส่งเป็น string ตั้งใจ: float ทำ 1234.10 กลายเป็น 1234.0999999 ได้
        และยอดเงินที่เพี้ยนแม้สตางค์เดียวคือเรื่องใหญ่เมื่อเทียบกับใบเสร็จ
        """

        def val(v):
            if isinstance(v, Decimal):
                return f"{v:.2f}"
            if isinstance(v, date):
                return v.isoformat()
            return v

        def walk(o):
            if isinstance(o, dict):
                return {k: walk(v) for k, v in o.items()}
            if isinstance(o, list):
                return [walk(x) for x in o]
            return val(o)

        return walk(asdict(self))
