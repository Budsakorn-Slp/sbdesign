"""ตรวจรหัสพนักงาน + PIN กับ SAP CRM ผ่าน rfc_api — POST /v1/auth/login

endpoint นี้รับได้ทั้งลูกค้าและพนักงาน (API แยกเอง) แต่ฝั่งเราเรียกเฉพาะตอนพนักงานล็อกอิน
ถ้า API ตอบว่าเป็น "customer" ถือว่าไม่ผ่าน — หน้าพนักงานไม่ใช่ทางเข้าของลูกค้า

ข้อที่ต้องรู้ (จากเอกสาร API.md ข้อ 5):
- ไม่ผ่านทุกกรณีได้ 401 LOGIN_FAILED ข้อความเดียวกันหมด — เราก็ไม่แยกต่อ
- ผิดเกิน 5 ครั้งต่อ login_id ฝั่ง API ล็อก 15 นาที ตอบ 429 LOGIN_LOCKED (+ detail.retry_after)
- pernr ที่ได้กลับมาเติม 0 ครบ 8 หลักแล้ว ส่งต่อเข้า SALES_EMPLOYEE ได้ตรงๆ
- PIN ห้ามลง log ไม่ว่าฝั่งไหน
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

from app.core.config import get_settings

log = logging.getLogger("sb.sap.auth")


@dataclass(frozen=True)
class SapEmployee:
    pernr: str            # 8 หลัก เติม 0 แล้ว
    name: str
    sales_office: str     # VKBUR
    sales_group: str      # VKGRP = showroom ที่ประจำ
    distr_chan: str       # VTWEG


class SapLoginFailed(Exception):
    """รหัส/PIN ไม่ถูก หรือไม่ใช่พนักงาน"""


class SapLoginLocked(Exception):
    def __init__(self, retry_after: int | None):
        super().__init__("locked")
        self.retry_after = retry_after


class SapAuthUnavailable(Exception):
    """ต่อ API ไม่ได้ / timeout / ตอบผิดรูป — ไม่ใช่ความผิดของคนกรอก"""


def enabled() -> bool:
    return bool(get_settings().sap_auth_url)


def login(login_id: str, password: str) -> SapEmployee:
    s = get_settings()
    req = urllib.request.Request(
        s.sap_auth_url,
        data=json.dumps({"login_id": login_id, "password": password}).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": s.sap_api_key,
                 "X-Request-Id": f"sbweb-{uuid.uuid4().hex[:12]}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=s.sap_auth_timeout_seconds) as r:
            body = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise SapLoginFailed() from e
        if e.code == 429:
            try:
                ra = json.loads(e.read().decode(errors="replace"))["error"]["detail"].get("retry_after")
            except (KeyError, ValueError, AttributeError):
                ra = None
            raise SapLoginLocked(int(ra) if ra else None) from e
        log.warning("SAP login ตอบ %s", e.code)
        raise SapAuthUnavailable(f"SAP ตอบ {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        log.warning("ต่อ SAP login ไม่ได้: %s", e)
        raise SapAuthUnavailable(str(e)) from e

    if body.get("type") != "employee":
        raise SapLoginFailed()
    p = body.get("profile") or {}
    pernr = str(p.get("pernr") or "").strip()
    if not pernr:
        raise SapAuthUnavailable("ไม่มี pernr ในคำตอบ")
    return SapEmployee(
        pernr=pernr.zfill(8),
        name=str(p.get("display_name") or "").strip(),
        sales_office=str(p.get("sales_office") or "").strip(),
        sales_group=str(p.get("sales_group") or "").strip(),
        distr_chan=str(p.get("distribution_channel") or "").strip(),
    )
