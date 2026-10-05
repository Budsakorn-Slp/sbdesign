"""gateway จำลอง — ใช้ตอนยังไม่ได้คีย์จากธนาคาร

พาลูกค้าไปหน้า /pay/{payment_no}/bank ของเราเอง ซึ่งเลียนแบบหน้าธนาคารและมีปุ่มให้เลือก
ผลได้ทั้งสามทาง (สำเร็จ/ปฏิเสธ/ยกเลิก) · ไม่มีเงินเคลื่อนไหวจริง
"""
from __future__ import annotations

from app.integrations.payment.base import ChargeRequest, ChargeResult


def _qr_payload(no: str, amount) -> str:
    """EMVCo จำลอง — หน้าเว็บเอาไปวาดเป็น QR ได้ แต่สแกนจ่ายจริงไม่ได้"""
    return f"00020101021229370016A000000677010111011300000000000053037645402{amount:.2f}5802TH6304{no[-4:]}"


class MockGateway:
    name = "mock"

    def charge(self, req: ChargeRequest) -> ChargeResult:
        return ChargeResult(
            provider_ref=f"mockpsp_{req.payment_no.replace('-', '').lower()}",
            redirect_url=f"/pay/{req.payment_no}/bank",
            qr_payload=_qr_payload(req.payment_no, req.amount) if req.method == "qr_promptpay" else None,
        )

    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> bool:
        # ของจำลองเซ็นด้วยกุญแจของเราเอง — ตรวจจริงอยู่ใน payment_service.sign()
        return True
