"""ดึงรายชื่อสินค้า + ราคา/ส่วนลดจาก SAP — ZAIBAPI_MATERIAL_GET_ALL ผ่าน RFC gateway

ต่างจาก material_stock/availability ตรงนี้คือ "ราคา" ไม่ใช่ "ของมีกี่ชิ้น"
และเป็นงานรายวันแบบยกชุด ไม่ใช่การถามสดตอนลูกค้ากดปุ่ม

สิ่งที่เรียนรู้จากการยิงของจริง (สำคัญตอนอ่านค่า):
- คำตอบมีสองตาราง: ET_MATERIALS (รหัส+ชื่อ) กับ ET_CONDITIONS (ราคาและส่วนลดทีละบรรทัด)
  สินค้าหนึ่งตัวมีได้หลายบรรทัดเงื่อนไข ต้องรวมเองที่ฝั่งเรา
- MATNR กลับมาเป็น 18 หลักเติมศูนย์หน้า ต้องตัดศูนย์ทิ้งก่อนเทียบกับรหัสในฐานเรา
- ขอรหัส 19xxxxxxx จะได้ตัวโชว์ 20xxxxxxx แถมมาด้วยเสมอ (SAP จับคู่ให้เอง)
  แต่ขอ 20 อย่างเดียวจะไม่ได้ 19 กลับมา — ทิศทางเดียว
- ตัวโชว์ (20) ไม่มีบรรทัดส่วนลด มีแต่ PR01 = ขายราคาป้ายเต็ม
- ทั้ง catalog ~1.1 ล้านแถว ขอทีเดียวไม่ไหว ต้องซอยเป็นช่วง (BT) ทีละก้อน

ชนิดเงื่อนไขที่พบจากการสำรวจทั้ง catalog (2026-10-01):
    PR01  THB  ราคาป้าย รวมภาษี          <- ฐานตั้งต้น
    ZD01  %    ส่วนลด Standard (%)
    ZD39  THB  ส่วนลด Standard (บาท)
    ZD52  %    ส่วนลด Member             <- ราคาสมาชิก ยังไม่สรุปสูตร ดู sync_sap_prices
    ZD36  THB  ส่วนลดชุด Set-Main 59
    ZD18  %    ส่วนลด GP
    ZD35  THB  ส่วนลดโปรโมชั่น-Mer
    ZD38  THB  ส่วนลดโปรเพิ่ม
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from app.core.config import Settings, get_settings
from app.integrations.sap.base import SapError

log = logging.getLogger("sb.sap.catalog")

BASE_KSCHL = "PR01"          # ราคาตั้งต้น มีได้บรรทัดเดียว
MEMBER_KSCHL = "ZD52"        # ส่วนลดสมาชิก — กันออกจากราคาปกติ (ดูหมายเหตุใน ETL)
DISPLAY_KSCHL = "ZD06"       # "ส่วนลดตัวโชว์" (ยืนยันชื่อจาก T685T)

# ส่วนลดตัวโชว์อยู่คนละช่องทางจำหน่ายกับราคาปกติ — ต้องยิงสองรอบ รอบละ VTWEG
# ค่าปกติ (18) ไม่มี ZD06 เลยสักแถว ส่วน 11 มีแต่ PR01 กับ ZD06
# รู้ได้จากการอ่าน A004 ตรงๆ ไม่ใช่เดา — ตอนแรกหาใน 18 แล้วไม่เจอจนนึกว่าไม่มีจริง
DISPLAY_VTWEG = "11"


def strip_matnr(raw: str) -> str:
    """'000000000019210764' -> '19210764' · รหัสที่เป็นตัวอักษร (A534) ไม่มีศูนย์นำอยู่แล้ว"""
    return (raw or "").lstrip("0") or (raw or "").strip()


@dataclass
class ConditionLine:
    kschl: str
    value: Decimal      # ติดลบ = ส่วนลด
    unit: str           # "THB" หรือ "%"
    text: str = ""


@dataclass
class MaterialPriceRow:
    matnr: str
    name: str = ""
    conditions: list[ConditionLine] = field(default_factory=list)

    def of(self, kschl: str) -> Decimal | None:
        for c in self.conditions:
            if c.kschl == kschl:
                return c.value
        return None

    @property
    def list_price(self) -> Decimal | None:
        """ราคาป้ายก่อนลด"""
        return self.of(BASE_KSCHL)

    def net_price(self, skip: tuple[str, ...] = (MEMBER_KSCHL,)) -> Decimal | None:
        """ราคาขายจริง = ราคาป้าย ลดเปอร์เซ็นต์ก่อน แล้วค่อยหักส่วนลดที่เป็นบาท

        ยืนยันกับของจริงแล้ว: 5,490 × (1 − 20%) − 2 = 4,390 ตรงกับราคาที่ขายอยู่
        ส่วนลดสมาชิก (ZD52) ถูกกันออกโดยปริยาย เพราะเป็นราคาคนละชั้นกับราคาปกติ
        """
        base = self.list_price
        if base is None:
            return None
        pct = sum((c.value for c in self.conditions
                   if c.unit == "%" and c.kschl not in skip and c.kschl != BASE_KSCHL), Decimal(0))
        flat = sum((c.value for c in self.conditions
                    if c.unit != "%" and c.kschl not in skip and c.kschl != BASE_KSCHL), Decimal(0))
        return (base * (Decimal(100) + pct) / Decimal(100)) + flat


class HttpMaterialCatalogClient:
    def __init__(self, url: str, api_key: str, timeout: float, head: dict[str, str]):
        self.url, self.api_key, self.timeout, self.head = url.rstrip("/"), api_key, timeout, head

    @classmethod
    def from_settings(cls, s: Settings) -> "HttpMaterialCatalogClient":
        if not s.sap_catalog_url:
            raise SapError("ยังไม่ได้ตั้ง SAP_CATALOG_URL ใน .env")
        return cls(s.sap_catalog_url, s.sap_api_key, s.sap_catalog_timeout_seconds, {
            "SALES_ORGANIZATION": str(s.sap_sales_org),
            "DISTRIBUTION_CHANNEL": str(s.sap_distr_chan),
            "DIVISION": str(s.sap_division),
        })

    def fetch_range(self, low: str, high: str | None = None,
                    vtweg: str | None = None) -> list[MaterialPriceRow]:
        """ขอหนึ่งช่วงรหัส — high=None คือขอรหัสเดียว · vtweg เปลี่ยนช่องทางจำหน่ายได้"""
        rng = {"SIGN": "I", "OPTION": "BT" if high else "EQ", "LOW": low}
        if high:
            rng["HIGH"] = high
        head = dict(self.head)
        if vtweg:
            head["DISTRIBUTION_CHANNEL"] = vtweg
        data = self._post({**head, "IT_MATERIALS": [rng]})

        rows: dict[str, MaterialPriceRow] = {}
        for m in data.get("ET_MATERIALS") or []:
            code = strip_matnr(m.get("MATNR", ""))
            if code:
                rows[code] = MaterialPriceRow(matnr=code, name=(m.get("MAKTX") or "").strip())
        for c in data.get("ET_CONDITIONS") or []:
            code = strip_matnr(c.get("MATNR", ""))
            if not code:
                continue
            # เงื่อนไขอาจมาก่อนรายชื่อ หรือมีรหัสที่ไม่มีใน ET_MATERIALS — สร้างแถวรอไว้
            row = rows.setdefault(code, MaterialPriceRow(matnr=code))
            row.conditions.append(ConditionLine(
                kschl=(c.get("KSCHL") or "").strip(),
                value=Decimal(str(c.get("KBETR") or 0)),
                unit=(c.get("KONWA") or "").strip(),
                text=(c.get("VTEXT") or "").strip(),
            ))
        return list(rows.values())

    def _post(self, params: dict) -> dict:
        body = json.dumps({"params": params}).encode()
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
            # เลขอ้างอิงของเรา เวลามีปัญหาทีมดูแล SAP จะค้น log ด้วยเลขนี้ได้
            "X-Request-Id": f"sbweb-cat-{uuid.uuid4().hex[:12]}",
        }
        try:
            with urllib.request.urlopen(urllib.request.Request(self.url, data=body, headers=headers),
                                        timeout=self.timeout) as r:
                return json.load(r).get("data") or {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            if e.code == 503:
                raise SapError(f"ระบบ SAP กำลังหนาแน่น (รอ {e.headers.get('Retry-After') or '?'} วินาที)") from e
            try:
                err = json.loads(raw)["error"]
                raise SapError(f"{err['code']}: {err['message']}") from e
            except (KeyError, ValueError):
                raise SapError(f"SAP ตอบ {e.code}: {raw[:200]}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise SapError(f"ต่อ SAP ไม่ได้: {e}") from e


def get_material_catalog_client() -> HttpMaterialCatalogClient:
    return HttpMaterialCatalogClient.from_settings(get_settings())
