"""เช็คสต็อกรวมทุกสาขา — ZAIBAPI_MATERIAL_STOCK ผ่าน RFC gateway (POST /v1/rfc/material-stock)

ต่างจาก availability.py ตรงคำถามที่ถาม:
  availability.py = "ลูกค้ารายนี้รับของวันนั้นได้กี่ชิ้น" ต้องระบุลูกค้า/sales org/สาขา
                    ใช้ตอนขายจริง เพราะ SAP จำลองทั้งใบและหักของที่บรรทัดก่อนหน้าจองไปแล้ว
  ไฟล์นี้        = "ของทั้งบริษัทมีเท่าไหร่" ใส่แค่รหัสสินค้า ระบบไล่เช็คทุกสาขาให้เอง
                    ใช้เติมตัวเลขให้หน้ารายการสินค้า ไม่ใช้ตัดสินตอนขาย

สิ่งที่เรียนรู้จากการยิงของจริง (สำคัญตอนอ่านค่า):
- ตอบกลับ "มากกว่า" ที่ขอได้ — สินค้าชุด (sales BOM) ถูกแตก component ออกมาเป็นแถวเพิ่ม
  (ขอ 40 รหัส ได้กลับ 42 แถว) จึงห้าม map ตามตำแหน่ง ต้องจับคู่ด้วยรหัสเสมอ
- AVAILABLE_QTY = 999 ต่อสาขา คือค่าที่ SAP ตั้งไว้แปลว่า "ไม่คุมสต็อก สั่งได้เสมอ"
  ไม่ใช่ของจริง 999 ชิ้น · เจอในหมวดสั่งทำ (เตียงสั่งทำ/โซฟาสั่งทำ) แบบ 100%
  ยอดรวมจึงออกมาเป็นพหุคูณของ 999 (30,969 = 31 สาขา × 999) ถ้าเอาไปโชว์ตรงๆ หน้าเว็บพัง
- error ทางธุรกิจมากับ HTTP 200 ใน MESSAGES ต้องเช็คทุกครั้ง ไม่ใช่ดูแค่ status
- MATERIAL ที่ตอบกลับเป็นรูป 18 หลักเติมศูนย์หน้า ต้องตัดศูนย์ก่อนใช้
"""
import json
import logging
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import date

from app.core.config import Settings, get_settings
from app.integrations.sap.base import SapError

log = logging.getLogger("sb.sap.stock")

# ค่าที่ SAP ใช้บอกว่า "สินค้าตัวนี้ไม่คุมสต็อก" — ดูคอมเมนต์หัวไฟล์
NOT_STOCKED_QTY = 999


@dataclass
class SiteStock:
    """ของที่สาขาหนึ่ง — ชื่อสาขามากับคำตอบของ SAP (ฟิลด์ NAME)

    บางแถวชื่อว่าง เช่น PLANT 1000 ซึ่งเป็นคลัง ไม่ใช่โชว์รูมที่ลูกค้าเดินเข้าไปดูของได้
    คนเรียกเป็นคนตัดสินว่าจะโชว์ตัวไหน ตรงนี้ส่งกลับไปให้ครบตามที่ SAP ตอบ
    """

    plant_code: str
    name: str
    available: int


@dataclass
class StockLine:
    """ของหนึ่งรหัส รวมทุกสาขาแล้ว"""

    matnr: str
    available: int  # มีพร้อมส่งตอนนี้ (0 เมื่อเป็นสินค้าสั่งทำ — ดู made_to_order)
    committed: int  # จะเข้ามาเพิ่ม
    committed_date: date | None
    made_to_order: bool = False  # SAP ตอบ 999 = สั่งได้เสมอ ไม่ต้องรอสต็อก
    sites: list["SiteStock"] = field(default_factory=list)  # เฉพาะสาขาที่มีของ


def _matnr(raw: str) -> str:
    return (raw or "").lstrip("0") or "0"


def _date(raw: str) -> date | None:
    raw = (raw or "").strip()
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))
    except ValueError:
        return None


def _qty(v) -> int:
    return int(float(v or 0))


class HttpMaterialStockClient:
    def __init__(self, url: str, api_key: str, timeout: float):
        self.url, self.api_key, self.timeout = url.rstrip("/"), api_key, timeout

    @classmethod
    def from_settings(cls, s: Settings) -> "HttpMaterialStockClient":
        return cls(s.sap_stock_url, s.sap_api_key, s.sap_stock_timeout_seconds)

    def _post(self, body: dict, fresh: bool) -> dict:
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
            # ส่งเลขอ้างอิงของเราไปทุกครั้ง เวลามีปัญหาทีมดูแล SAP จะค้น log ด้วยเลขนี้ได้
            "X-Request-Id": f"sbweb-{uuid.uuid4().hex[:12]}",
        }
        if fresh:  # ตอน checkout ต้องได้เลขสด ไม่เอา cache 60 วิของ gateway
            headers["Cache-Control"] = "no-cache"
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            if e.code == 503:  # คิวเต็ม — เอกสารบอกให้รอตาม Retry-After อย่ายิงซ้ำทันที
                raise SapError(f"ระบบ SAP กำลังหนาแน่น (รอ {e.headers.get('Retry-After') or '?'} วินาที)") from e
            try:
                err = json.loads(raw)["error"]
                raise SapError(f"{err['code']}: {err['message']}") from e
            except (KeyError, ValueError):
                raise SapError(f"SAP ตอบ {e.code}: {raw[:200]}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise SapError(f"ต่อ SAP ไม่ได้: {e}") from e

    def check(self, matnrs: list[str], req_date: date, fresh: bool = False) -> dict[str, StockLine]:
        """คืน dict รหัส -> ของที่มี · รหัสที่ SAP ไม่รู้จักจะไม่มี key"""
        if not matnrs:
            return {}
        iso = req_date.isoformat()
        body = {"params": {"REQUEST_ITEMS": [{"MATERIAL": m, "REQ_QUANTITY": 1, "REQ_DATE": iso} for m in matnrs]}}
        t0 = time.monotonic()
        res = self._post(body, fresh)
        data = res.get("data") or {}

        errs = [m.get("MESSAGE") for m in (data.get("MESSAGES") or []) if m.get("TYPE") == "E"]
        if errs:
            raise SapError("; ".join(filter(None, errs))[:300])

        # สาขาไหนตอบ 999 = สินค้าตัวนั้นไม่คุมสต็อก (ดูคอมเมนต์หัวไฟล์)
        # เช็คจากยอดรายสาขา ไม่ใช่ยอดรวม เพราะยอดรวมเป็น 999 × จำนวนสาขา ซึ่งเดาย้อนกลับไม่ได้
        sites_raw = data.get("STOCK_ON_SITES") or []
        not_stocked = {
            _matnr(s.get("MATERIAL", "")) for s in sites_raw if _qty(s.get("AVAILABLE_QTY")) >= NOT_STOCKED_QTY
        }
        # เก็บเฉพาะสาขาที่มีของ — SAP ตอบ 32 แถวต่อรหัสเสมอ ส่วนใหญ่เป็นศูนย์
        by_matnr: dict[str, list[SiteStock]] = {}
        for srow in sites_raw:
            qty = _qty(srow.get("AVAILABLE_QTY"))
            if qty <= 0 or qty >= NOT_STOCKED_QTY:
                continue
            by_matnr.setdefault(_matnr(srow.get("MATERIAL", "")), []).append(
                SiteStock(plant_code=(srow.get("PLANT") or "").strip(), name=(srow.get("NAME") or "").strip(), available=qty)
            )
        out: dict[str, StockLine] = {}
        for r in data.get("STOCK_REQUIREMENTS") or []:
            m = _matnr(r.get("MATERIAL", ""))
            mto = m in not_stocked
            out[m] = StockLine(
                matnr=m,
                available=0 if mto else _qty(r.get("AVAILABLE_QTY")),
                committed=0 if mto else _qty(r.get("COMMITTED_QTY")),
                committed_date=None if mto else _date(r.get("COMMITTED_DATE", "")),
                made_to_order=mto,
                sites=[] if mto else sorted(by_matnr.get(m, []), key=lambda x: (-x.available, x.name)),
            )
        log.info("material-stock: ขอ %d รหัส ได้ %d (cached=%s) ใน %.1f วิ",
                 len(matnrs), len(out), res.get("cached"), time.monotonic() - t0)
        return out


class MockMaterialStockClient:
    """ใช้ตอน dev/test — เลขคงที่ต่อรหัส ไม่ต้องต่อ SAP จริง"""

    def check(self, matnrs: list[str], req_date: date, fresh: bool = False) -> dict[str, StockLine]:
        import hashlib

        out: dict[str, StockLine] = {}
        for m in matnrs:
            seed = int(hashlib.md5(m.encode()).hexdigest()[:8], 16)
            bucket = seed % 100
            if bucket < 8:
                out[m] = StockLine(m, 0, 0, None)
            elif bucket < 15:
                out[m] = StockLine(m, 0, seed % 9 + 2, req_date)
            elif bucket < 22:
                out[m] = StockLine(m, 0, 0, None, made_to_order=True)
            else:
                out[m] = StockLine(m, seed % 40 + 1, 0, None)
        return out


def get_material_stock_client():
    s = get_settings()
    if s.sap_stock_url and s.sap_api_key:
        return HttpMaterialStockClient.from_settings(s)
    return MockMaterialStockClient()
