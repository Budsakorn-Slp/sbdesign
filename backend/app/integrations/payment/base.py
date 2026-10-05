"""ช่องทางรับชำระเงิน — สัญญากลางที่ payment_service คุยด้วย

มีไว้ให้สลับจาก mock ไปเป็น K-Payment Gateway ของกสิกรได้โดยไม่ต้องแก้ payment_service
แบบเดียวกับฝั่ง SAP ที่มี MockSapClient กับ HttpSapClient อยู่หลังหน้าตาเดียวกัน

ขอบเขตของ gateway: "สร้างรายการเก็บเงิน แล้วบอกว่าจะพาลูกค้าไปไหนต่อ"
เรื่องสถานะ/ใบเสนอราคา/การส่ง SO เข้า SAP เป็นงานของ payment_service ไม่ใช่ของตรงนี้
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


class PaymentError(Exception):
    """ติดต่อ gateway ไม่ได้ หรือ gateway ตอบว่าสร้างรายการไม่ได้"""


@dataclass
class ChargeRequest:
    """สิ่งที่ต้องบอก gateway เพื่อเปิดรายการเก็บเงินหนึ่งรายการ"""

    payment_no: str          # เลขอ้างอิงฝั่งเรา — ใช้จับคู่ตอน webhook ตอบกลับ
    amount: Decimal
    method: str              # qr_promptpay | card | installment
    description: str         # ขึ้นบนหน้าจอธนาคารและในใบแจ้งยอดบัตร
    customer_name: str | None = None
    customer_email: str | None = None
    return_url: str = ""     # จ่ายเสร็จ/ยกเลิก แล้วธนาคารพากลับมาที่นี่


@dataclass
class ChargeResult:
    """คำตอบจาก gateway

    redirect_url  พาลูกค้าออกไปหน้าธนาคาร (บัตร/ผ่อน) — ของจริงเป็นโดเมนของธนาคาร
    qr_payload    สตริง EMVCo สำหรับวาด QR เอง (PromptPay)
    อย่างน้อยต้องมีอย่างใดอย่างหนึ่ง ไม่งั้นลูกค้าจ่ายไม่ได้
    """

    provider_ref: str
    redirect_url: str | None = None
    qr_payload: str | None = None
    raw: dict | None = None


class PaymentGateway(Protocol):
    name: str

    def charge(self, req: ChargeRequest) -> ChargeResult: ...

    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> bool:
        """ข้อความที่ยิงเข้ามาเป็นของ gateway จริงไหม

        แยกจาก charge เพราะแต่ละเจ้าเซ็นคนละแบบ (header คนละชื่อ อัลกอคนละตัว)
        คืน False ไว้ก่อนเสมอเมื่อไม่แน่ใจ — ยอมพลาดของจริงดีกว่ารับของปลอม
        """
        ...
