"""ตัวส่งจำลอง — พิมพ์ออก console แทนการยิง SMS จริง

ใช้ตอน dev/เทส · ไม่มีค่าใช้จ่าย ไม่รบกวนเบอร์จริง และเห็นรหัสได้ทันทีในหน้าต่างที่รัน backend
"""
import logging

log = logging.getLogger("sb.sms")


class MockSmsClient:
    def send(self, phone: str, text: str) -> None:
        log.info("[MOCK SMS] -> %s : %s", phone, text)
