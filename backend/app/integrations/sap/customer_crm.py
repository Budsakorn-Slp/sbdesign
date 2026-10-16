"""ทะเบียนลูกค้าจริงใน SAP CRM ผ่าน rfc_api — ค้น (customer-search) + สร้างใหม่ (รอ API)

ค้น: POST /v1/rfc/customer-search  (ZBAPI_BUPA_SEARCH)
  ส่งเบอร์ / อีเมล / เลขลูกค้า → ได้ business partner ทุก role ของคนนั้น

  กับดักที่ต้องจัดการเอง (จากเอกสาร API.md ข้อ 4.8 + ลองยิงจริง):
  - ค้นแบบ "ใกล้เคียง" ไม่ใช่ตรงตัว — ค้นเบอร์หนึ่งได้ 63 แถว มีเบอร์อื่นปนมาเพียบ
    ต้องเทียบเบอร์ให้ตรงเป๊ะเองทั้ง TELEPHONE / MOBILE_TEL / MOBILE_TEL2
  - คนเดียวได้หลายแถวตาม role — เลขขึ้นต้น 11 = ลูกค้า (ใช้เป็น CUSTOMER_ID ของเอกสาร)
    17 = bill-to · 18 = ship-to · 19 = อื่นๆ → เอาเฉพาะ 11 ไม่งั้นเอกสารออกผิดคน
  - เบอร์ที่คนใช้ซ้ำเยอะช้ามาก (เคยเจอ 56 วิ / 1,184 แถว) → timeout ต้องเผื่อ
  - ผลมีข้อมูลส่วนบุคคล (PDPA) — ห้ามลง log
  - เบอร์เดียวผูกหลายลูกค้าได้จริง (เบอร์ทดสอบ 0860140944 ตรง 49 แถว / ลูกค้าเลข 11 หลายสิบราย —
    ส่วนใหญ่เป็นเบอร์บ้าน/เบอร์ร้านที่กรอกแทน) จะเลือก "ใหม่สุด" หรือ "แถวแรก" ไม่ได้
  - ET_CUSTATTR: ทีม SAP ยังไม่สรุปความหมาย แต่จากเบอร์ทดสอบชี้ตรงเจ้าของจริง (1100467950)
    → ใช้เป็นตัว "จัดอันดับ" เท่านั้น (เจ้าของขึ้นก่อน) ไม่ใช้ตัดรายอื่นทิ้ง

สร้าง: TODO — ทีม SAP กำลังทำ API สร้างเลขลูกค้า (สร้างที่ CRM แล้ว sync ไป ERP เอง)
  เตรียมช่องไว้ที่ create_customer() · มีสเปกเมื่อไหร่เติมตรงนั้นที่เดียว
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

from app.core.config import get_settings
from app.integrations.sap.base import CustomerDTO, SapError

log = logging.getLogger("sb.sap.customer")

CUSTOMER_PREFIX = "11"  # Domestic Trade Retail Customer — เลขที่ใช้เป็น CUSTOMER_ID ได้


def enabled() -> bool:
    return bool(get_settings().sap_customer_url)


def create_enabled() -> bool:
    return bool(get_settings().sap_customer_create_url)


def _digits(s: str | None) -> str:
    d = "".join(ch for ch in (s or "") if ch.isdigit())
    # +66 81 234 5678 → 0812345678
    if d.startswith("66") and len(d) == 11:
        d = "0" + d[2:]
    return d


def _post(url: str, params: dict, timeout: float) -> dict:
    s = get_settings()
    req = urllib.request.Request(
        url, data=json.dumps({"params": params}).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": s.sap_api_key,
                 "X-Request-Id": f"sbweb-{uuid.uuid4().hex[:12]}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SapError(f"SAP ตอบ {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise SapError(f"ต่อ SAP ไม่ได้: {e}") from e


def _params_for(key: str) -> tuple[dict, str] | None:
    """เลือกช่องค้นจากรูปแบบที่พิมพ์ — คืน (params, ชนิด) · ชื่อคนไม่ค้นที่นี่ (ผลกว้างเกินจะเลือกให้ถูก)"""
    k = (key or "").strip()
    if not k:
        return None
    if "@" in k:
        return {"IV_EMAIL": k}, "email"
    d = _digits(k)
    if d.startswith(CUSTOMER_PREFIX) and len(d) == 10:
        return {"IS_CENTRALDATA": {"PARTNER": d}}, "partner"
    if 9 <= len(d) <= 10:
        return {"IV_TELEPHONE": d}, "phone"
    return None


_POSTCODE = re.compile(r"(\d{5})\s*$")


def _to_dto(r: dict, phone: str | None) -> CustomerDTO:
    addr = " ".join(str(r.get("ADDRESS") or "").split()) or None
    m = _POSTCODE.search(addr or "")
    name = " ".join(x for x in (str(r.get("FIRSTNAME") or "").strip(), str(r.get("LASTNAME") or "").strip()) if x)
    return CustomerDTO(
        sap_customer_no=str(r.get("PARTNER") or "").lstrip("0"),
        name=name or str(r.get("SEARCHTERM1") or "").strip(),
        points=0,  # CRM ไม่ได้ให้แต้มมา
        phone=phone or _digits(r.get("MOBILE_TEL")) or _digits(r.get("TELEPHONE")) or None,
        email=(str(r.get("E_MAIL") or "").strip().lower() or None),
        address=addr,
        postcode=m.group(1) if m else None,
    )


def search(key: str) -> list[CustomerDTO]:
    """ลูกค้า (เลขขึ้นต้น 11) ที่ตรงกับเบอร์/อีเมล/เลขลูกค้านี้แบบเป๊ะ — เจ้าของเบอร์ขึ้นก่อน"""
    return _search(key)[0]


def _search(key: str) -> tuple[list[CustomerDTO], bool]:
    """คืน (รายที่ตรง, รายแรกเป็นเจ้าของตาม ET_CUSTATTR หรือไม่)"""
    got = _params_for(key)
    if not got:
        return [], False
    params, kind = got
    body = _post(get_settings().sap_customer_url, params, get_settings().sap_customer_timeout_seconds)
    data = body.get("data") or {}
    errs = [m.get("MESSAGE") for m in (data.get("ET_RETURN") or []) if m.get("TYPE") in ("E", "A")]
    if errs:
        raise SapError("; ".join(filter(None, errs))[:200])

    want_phone = _digits(key) if kind == "phone" else None
    want_email = key.strip().lower() if kind == "email" else None
    want_partner = _digits(key) if kind == "partner" else None
    rows = []
    for r in data.get("ET_SEARCHRESULT") or []:
        partner = str(r.get("PARTNER") or "").lstrip("0")
        if not partner.startswith(CUSTOMER_PREFIX):
            continue
        # ถูกบล็อก / เก็บเข้าคลังแล้ว — ไม่ใช่ลูกค้าที่ใช้งานอยู่
        if str(r.get("CENTRALBLOCK") or "").strip() or str(r.get("CENTRALARCHIVINGFLAG") or "").strip():
            continue
        if want_phone and want_phone not in {_digits(r.get(f)) for f in ("TELEPHONE", "MOBILE_TEL", "MOBILE_TEL2")}:
            continue
        if want_email and str(r.get("E_MAIL") or "").strip().lower() != want_email:
            continue
        if want_partner and partner != want_partner:
            continue
        rows.append(r)
    owners = {str(x.get("PARTNER") or "").lstrip("0") for x in data.get("ET_CUSTATTR") or []}

    def rank(r: dict):
        p = str(r.get("PARTNER") or "").lstrip("0")
        on_mobile = bool(want_phone) and want_phone in {_digits(r.get("MOBILE_TEL")), _digits(r.get("MOBILE_TEL2"))}
        # เจ้าของ (ET_CUSTATTR) ก่อน → เบอร์อยู่ในช่องมือถือ (ของตัวเอง) → สร้างล่าสุด
        return (p not in owners, not on_mobile, -int(str(r.get("CRDAT") or "0") or 0))

    rows.sort(key=rank)
    first_is_owner = bool(rows) and str(rows[0].get("PARTNER") or "").lstrip("0") in owners
    seen: set[str] = set()
    out: list[CustomerDTO] = []
    for r in rows:
        dto = _to_dto(r, want_phone)
        if dto.sap_customer_no not in seen:
            seen.add(dto.sap_customer_no)
            out.append(dto)
    return out, first_is_owner


def get_customer(key: str) -> CustomerDTO | None:
    """หนึ่งรายที่ "มั่นใจ" ว่าใช่ — เลขลูกค้า/อีเมลตรงตัว, เบอร์ที่มีรายเดียว หรือเจ้าของตาม ET_CUSTATTR

    เบอร์ที่ผูกหลายรายแล้วแยกเจ้าของไม่ได้ → None (ไม่เดา) · ผูกผิดคน = เห็นข้อมูลของคนอื่น
    หน้าพนักงานใช้ search() โชว์ทุกรายให้เลือก แล้วผูกด้วยเลขลูกค้า (ซึ่งตรงตัวเสมอ)
    """
    found, owner = _search(key)
    if not found:
        return None
    if len(found) == 1 or owner or _params_for(key)[1] != "phone":
        return found[0]
    return None


@dataclass
class NewCustomer:
    """ข้อมูลที่จะส่งไปสร้างเลขลูกค้า — ช่องจริงรอสเปกจากทีม SAP (account group 11)"""

    first_name: str
    last_name: str
    phone: str
    email: str | None = None
    address: str | None = None
    postcode: str | None = None
    tax_id: str | None = None


class CustomerCreateNotReady(Exception):
    """ยังไม่มี API สร้างเลขลูกค้า (SAP_CUSTOMER_CREATE_URL ว่าง)"""


def create_customer(c: NewCustomer) -> str:
    """สร้างลูกค้าใหม่ใน SAP แล้วคืนเลขลูกค้า (ขึ้นต้น 11)

    TODO: รอสเปก API จากทีม SAP — ตอนนี้ยังไม่ได้ยิงจริง
    สิ่งที่ต้องเช็คตอนเติม: ชื่อพารามิเตอร์ · ตอบเลขกลับมาทันทีไหม · sync ไป ERP นานแค่ไหน
    (ลูกค้ายืนรอ ถ้าหน่วงต้องมีขั้นรอก่อนเรียก webcart-quotation) · กันสร้างซ้ำด้วยอะไร
    และก่อนสร้างต้องค้นด้วยเบอร์ก่อนเสมอ ไม่งั้นได้ลูกค้าซ้ำใน SAP
    """
    if not create_enabled():
        raise CustomerCreateNotReady()
    raise CustomerCreateNotReady()  # มี URL แล้วแต่ยังไม่รู้รูปแบบคำขอ — เติมเมื่อได้สเปก
