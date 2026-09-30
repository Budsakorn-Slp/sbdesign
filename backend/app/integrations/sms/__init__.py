"""factory: สลับตัวส่ง SMS ด้วย env เดียว SMS_MODE=mock|http

วิธีต่อผู้ให้บริการจริง (ThaiBulkSMS / SMS Master / Twilio ฯลฯ):
  1. เขียน app/integrations/sms/<ชื่อเจ้า>.py ที่มี method send(phone, text) ตาม SmsClient
  2. เพิ่มสาขาใน get_sms_client() ข้างล่าง
  3. ตั้ง SMS_MODE ใน .env
โค้ดที่เรียกใช้ (auth_service.issue_otp) ไม่ต้องแก้อะไรเลย
"""
from functools import lru_cache

from app.core.config import get_settings
from app.integrations.sms.base import SmsClient, SmsError  # noqa: F401


@lru_cache
def get_sms_client() -> SmsClient:
    mode = get_settings().sms_mode.lower()
    if mode == "mock":
        from app.integrations.sms.mock import MockSmsClient

        return MockSmsClient()
    if mode == "http":
        from app.integrations.sms.http import HttpSmsClient

        return HttpSmsClient.from_settings(get_settings())
    raise RuntimeError(f"SMS_MODE ไม่รู้จัก: {mode} (ใช้ mock | http)")
