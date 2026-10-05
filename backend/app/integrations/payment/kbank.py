"""K-Payment Gateway (กสิกรไทย) — โครงไว้รอคีย์ sandbox

สถานะ: **ยังต่อไม่ได้** เพราะยังไม่มีคีย์และยังไม่ได้เอกสาร API มาเทียบ
ตั้ง PAYMENT_PROVIDER=kbank แล้วจะใช้ตัวนี้ · ไม่ได้ตั้งคีย์ไว้มันจะตีกลับทันทีพร้อม
บอกว่าขาดอะไร ไม่ใช่เงียบๆ แล้วปล่อยให้ลูกค้าไปตันที่หน้าจ่ายเงิน

ที่ต้องขอจากธนาคาร/ทีมที่ดูแลบัญชีร้านค้า:
  1. Merchant ID
  2. API key ฝั่ง public (ใช้กับ kpayment.js บนหน้าเว็บ) และ secret (ใช้ฝั่งเซิร์ฟเวอร์)
  3. URL ของ sandbox กับของจริง
  4. รูปแบบ payload ตอนสร้างรายการ และชื่อฟิลด์ที่ตอบกลับ
  5. วิธีเซ็น webhook (ชื่อ header + อัลกอริทึม) เพื่อยืนยันว่าข้อความมาจากธนาคารจริง

ข้อ 4 กับ 5 คือสองข้อที่เดาเองไม่ได้ — เดาผิดแล้วจะรู้ตอนเงินไม่เข้า จึงเว้นไว้ให้
เติมตอนได้เอกสาร แทนที่จะเขียนโครงสร้างมั่วๆ ไว้ให้ดูเหมือนเสร็จแล้ว
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import Settings
from app.integrations.payment.base import ChargeRequest, ChargeResult, PaymentError

log = logging.getLogger("sb.payment.kbank")

# กสิกรแยกโดเมน sandbox กับของจริง — ตั้งใน .env ไม่ฝังในโค้ด
# เผลอใช้ของจริงตอนทดสอบแล้วตัดเงินลูกค้าจริงคือความผิดพลาดที่ย้อนกลับยาก
SANDBOX_HINT = "https://dev-kpaymentgateway.kasikornbank.com"


class KBankGateway:
    name = "kbank"

    def __init__(self, base_url: str, secret_key: str, merchant_id: str, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.secret_key = secret_key
        self.merchant_id = merchant_id
        self.timeout = timeout

    @classmethod
    def from_settings(cls, s: Settings) -> "KBankGateway":
        missing = [k for k, v in (
            ("KBANK_BASE_URL", s.kbank_base_url),
            ("KBANK_SECRET_KEY", s.kbank_secret_key),
            ("KBANK_MERCHANT_ID", s.kbank_merchant_id),
        ) if not v]
        if missing:
            raise PaymentError(
                "ตั้ง PAYMENT_PROVIDER=kbank ไว้แต่ยังไม่ได้ใส่ค่า: " + ", ".join(missing)
                + f" (sandbox ของกสิกรคือ {SANDBOX_HINT})"
            )
        return cls(s.kbank_base_url, s.kbank_secret_key, s.kbank_merchant_id, s.kbank_timeout_seconds)

    def charge(self, req: ChargeRequest) -> ChargeResult:
        raise PaymentError(
            "ยังต่อ K-Payment Gateway ไม่ได้ — รอเอกสาร API และคีย์จากธนาคาร "
            "(ดูรายการที่ต้องขอในหัวไฟล์ app/integrations/payment/kbank.py)"
        )

    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> bool:
        # ยังไม่รู้ว่าธนาคารเซ็นด้วย header ชื่ออะไรและอัลกอริทึมไหน
        # คืน False ไว้ก่อน = ไม่รับข้อความใดๆ ดีกว่ารับของปลอมแล้วตัดสถานะว่าจ่ายแล้ว
        log.warning("verify_webhook ของ kbank ยังไม่ได้ทำ — ปฏิเสธข้อความทั้งหมดไว้ก่อน")
        return False

    def _post(self, path: str, body: dict) -> dict:
        """ตัวช่วยยิง HTTP — ยังไม่ถูกเรียกจนกว่าจะเติม charge() ให้เสร็จ"""
        url = f"{self.base_url}{path}"
        try:
            r = httpx.post(url, json=body, timeout=self.timeout,
                           headers={"Authorization": f"Bearer {self.secret_key}",
                                    "Content-Type": "application/json"})
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise PaymentError(f"ติดต่อ K-Payment Gateway ไม่ได้: {e}") from e
