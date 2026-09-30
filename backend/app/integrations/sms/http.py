"""ตัวส่ง SMS ผ่าน HTTP API — ตั้งค่าได้จาก .env โดยไม่ต้องเขียนโค้ดเพิ่ม

ผู้ให้บริการ SMS ในไทยส่วนใหญ่เป็น REST เหมือนกันหมด ต่างกันแค่ชื่อฟิลด์กับวิธีใส่กุญแจ
ตัวนี้จึงทำเป็น "แบบฟอร์มเปล่า" ให้กรอกผ่าน env แทนที่จะเขียน adapter ใหม่ทุกเจ้า

    SMS_MODE=http
    SMS_URL=https://api.thaibulksms.com/sms
    SMS_AUTH_HEADER=Authorization        # ชื่อ header ที่ใส่กุญแจ (เว้นว่าง = ไม่ใส่ header)
    SMS_API_KEY=Bearer xxxxx             # ค่าที่ใส่ใน header นั้น
    SMS_FIELD_TO=msisdn                  # ชื่อฟิลด์เบอร์ปลายทางใน body
    SMS_FIELD_TEXT=message               # ชื่อฟิลด์ข้อความ
    SMS_SENDER=SBDESIGN                  # ชื่อผู้ส่ง (ถ้าเจ้านั้นต้องการ)
    SMS_FIELD_SENDER=sender
    SMS_PHONE_FORMAT=local               # local=0812223333 · e164=+66812223333 · intl=66812223333

ถ้าเจ้าไหนมีรูปแบบแปลกกว่านี้ (เช่น XML หรือ query string) ให้เขียน adapter เฉพาะเจ้านั้น
ไฟล์ใหม่แล้วเพิ่มสาขาใน __init__.py — ไม่ต้องดัดตัวนี้จนอ่านไม่รู้เรื่อง
"""
import logging

import httpx

from app.core.config import Settings
from app.integrations.sms.base import SmsError

log = logging.getLogger("sb.sms")


class HttpSmsClient:
    def __init__(self, s: Settings):
        if not s.sms_url:
            raise RuntimeError("SMS_MODE=http แต่ยังไม่ได้ตั้ง SMS_URL")
        self.url = s.sms_url
        self.auth_header = s.sms_auth_header
        self.api_key = s.sms_api_key
        self.field_to = s.sms_field_to
        self.field_text = s.sms_field_text
        self.field_sender = s.sms_field_sender
        self.sender = s.sms_sender
        self.phone_format = s.sms_phone_format
        self.timeout = s.sms_timeout_seconds

    @classmethod
    def from_settings(cls, s: Settings) -> "HttpSmsClient":
        return cls(s)

    def _phone(self, phone: str) -> str:
        digits = "".join(ch for ch in phone if ch.isdigit())
        if self.phone_format == "local":
            return digits
        national = digits[1:] if digits.startswith("0") else digits
        return ("+66" if self.phone_format == "e164" else "66") + national

    def send(self, phone: str, text: str) -> None:
        body = {self.field_to: self._phone(phone), self.field_text: text}
        if self.sender and self.field_sender:
            body[self.field_sender] = self.sender
        headers = {self.auth_header: self.api_key} if self.auth_header and self.api_key else {}
        try:
            r = httpx.post(self.url, json=body, headers=headers, timeout=self.timeout)
            r.raise_for_status()
        except httpx.HTTPError as e:
            # ห้ามใส่ text ลง log — มี OTP อยู่ข้างใน หลุดลง log แล้วเท่ากับรหัสรั่ว
            log.warning("ส่ง SMS ไม่สำเร็จ (%s): %s", phone[-4:], e)
            raise SmsError(str(e)) from e
