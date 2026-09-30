"""SAP adapter แบบ HTTP — ตัวที่จะใช้จริงเมื่อฝั่งหลังบ้านเปิด endpoint ให้

ตอนนี้ทำเฉพาะ create_sales_order ซึ่งเป็นสิ่งเดียวที่ต้องยิงออกไปจากฝั่งเรา
ส่วนที่เหลือ (ค้นสินค้า / ลูกค้า / โปรโมชัน) ยังถอยไปใช้ mock เพราะยังไม่มี endpoint จริง
— แยกเป็นตัวๆ แบบนี้เพื่อให้ย้ายทีละอย่างได้ ไม่ต้องรอให้เสร็จครบแล้วค่อยสลับทั้งก้อน

ตั้งค่าใน .env:
    SAP_MODE=http
    SAP_SO_URL=https://sap-gw.sb.local/api/sales-order
    SAP_API_KEY=xxxxx
"""
import logging

import httpx

from app.core.config import Settings
from app.integrations.sap.base import SapError, SapSoResult
from app.integrations.sap.mock import MockSapClient
from app.integrations.sap.sales_order import SalesOrderDTO

log = logging.getLogger("sb.sap.so")

# ชื่อฟิลด์เลข SO ที่ยอมรับในคำตอบ — gateway แต่ละตัวตั้งชื่อไม่เหมือนกัน
# (VBELN เป็นชื่อฟิลด์จริงใน SAP SD ส่วนอีกสองตัวเป็นชื่อที่ REST wrapper มักใช้)
SO_KEYS = ("so_no", "sap_so_no", "VBELN", "vbeln", "sales_order")


class HttpSapClient(MockSapClient):
    """ของจริงเฉพาะ create_sales_order · ที่เหลือสืบทอด mock ไปก่อน

    สืบทอดจาก mock ตั้งใจ ไม่ใช่ความมักง่าย — ระบบยังต้องค้นสินค้า/เช็คลูกค้าได้ระหว่างที่
    endpoint อื่นยังไม่พร้อม ถ้าให้ method ที่ยังไม่มี endpoint โยน NotImplemented ทิ้ง
    ทั้งเว็บจะใช้ไม่ได้เลยตั้งแต่วันที่สลับเป็น http
    """

    def __init__(self, s: Settings):
        super().__init__()
        if not s.sap_so_url:
            raise RuntimeError("SAP_MODE=http แต่ยังไม่ได้ตั้ง SAP_SO_URL")
        self.url = s.sap_so_url
        self.api_key = s.sap_api_key
        self.timeout = s.sap_so_timeout_seconds

    @classmethod
    def from_settings(cls, s: Settings) -> "HttpSapClient":
        return cls(s)

    def create_sales_order_doc(self, order: SalesOrderDTO) -> SapSoResult:
        """ยิง payload เต็มใบไปสร้าง SO — คืนเลข SO ที่ SAP ออกให้

        ไม่ retry ที่นี่: คิว retry อยู่ชั้นบน (payment_service.push_to_sap) ซึ่งรู้ว่า
        ครั้งนี้เป็นครั้งที่เท่าไรและควรรอนานแค่ไหน · ยิงซ้ำเองตรงนี้จะซ้อนกันสองชั้น
        และเสี่ยงสร้าง SO ซ้ำถ้า SAP รับไปแล้วแต่ตอบกลับไม่ทัน
        """
        headers = {"X-API-Key": self.api_key} if self.api_key else {}
        try:
            r = httpx.post(self.url, json=order.to_payload(), headers=headers, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            raise SapError(f"ยิง SAP ไม่สำเร็จ: {e}") from e
        except ValueError as e:
            raise SapError(f"SAP ตอบกลับไม่ใช่ JSON: {e}") from e

        so = next((str(data[k]).strip() for k in SO_KEYS if data.get(k)), None)
        if not so:
            # ตอบ 200 แต่ไม่มีเลข SO = ไม่สำเร็จ ห้ามนับว่าผ่าน ไม่งั้นออร์เดอร์หายเงียบ
            msg = data.get("message") or data.get("error") or "SAP ไม่ได้คืนเลข Sales Order"
            log.warning("SAP ไม่คืนเลข SO (%s): %s", order.quotation_no, str(data)[:300])
            return SapSoResult(ok=False, sap_so_no=None, message=str(msg)[:500])
        return SapSoResult(ok=True, sap_so_no=so, message=data.get("message"))
