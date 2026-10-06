"""สร้าง Google Sheet จากแถวข้อมูล — ใช้ service account ของบริษัท

ทำไมไม่ใช้ไลบรารีของ Google: ใช้แค่ 4 เส้น (ขอ token · สร้างไฟล์ · เขียนค่า · แชร์)
httpx + PyJWT ที่มีอยู่แล้วพอ ไม่ต้องลากแพ็กเกจก้อนใหญ่เข้ามา

ลำดับ:
  1. เซ็น JWT ด้วยกุญแจของ service account → แลก access token
  2. สร้างไฟล์ชนิด spreadsheet ใน Shared Drive (Drive API)
  3. เขียนค่าลงชีต (Sheets API)
  4. แชร์สิทธิ์แก้ไขให้อีเมลของพนักงานที่กด
"""
from __future__ import annotations

import json
import time
from functools import lru_cache
from pathlib import Path

import httpx
import jwt

from app.core.config import get_settings

TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE = "https://www.googleapis.com/drive/v3"
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
SCOPES = "https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/spreadsheets"


class SheetsNotConfigured(Exception):
    pass


class SheetsError(Exception):
    pass


def configured() -> bool:
    s = get_settings()
    return bool(s.google_sa_file and s.google_sheets_folder_id and Path(s.google_sa_file).is_file())


@lru_cache
def _key(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _client() -> httpx.Client:
    # แยกเป็นฟังก์ชันให้เทสสลับเป็น MockTransport ได้ — เทสต้องไม่ยิง Google จริง
    return httpx.Client(timeout=20.0)


def _token(c: httpx.Client, sa: dict) -> str:
    now = int(time.time())
    assertion = jwt.encode({"iss": sa["client_email"], "scope": SCOPES, "aud": TOKEN_URL, "iat": now, "exp": now + 600},
                           sa["private_key"], algorithm="RS256")
    r = c.post(TOKEN_URL, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
    if r.status_code != 200:
        raise SheetsError(f"ขอสิทธิ์ Google ไม่สำเร็จ ({r.status_code})")
    return r.json()["access_token"]


def _cell(v):
    # Sheets รับแค่ string/ตัวเลข/บูลีน — None กลายเป็นช่องว่าง
    return "" if v is None else v


def create_sheet(title: str, rows: list[list], share_with: str | None) -> str:
    """สร้างชีตใหม่แล้วคืน URL · share_with = อีเมลที่จะได้สิทธิ์แก้ไข"""
    if not configured():
        raise SheetsNotConfigured()
    s = get_settings()
    sa = _key(s.google_sa_file)
    with _client() as c:
        h = {"Authorization": f"Bearer {_token(c, sa)}"}
        r = c.post(f"{DRIVE}/files", params={"supportsAllDrives": "true", "fields": "id"}, headers=h,
                   json={"name": title, "mimeType": "application/vnd.google-apps.spreadsheet",
                         "parents": [s.google_sheets_folder_id]})
        if r.status_code not in (200, 201):
            raise SheetsError(f"สร้างไฟล์ใน Google Drive ไม่สำเร็จ ({r.status_code})")
        sid = r.json()["id"]
        width = max((len(x) for x in rows), default=1)
        values = [[_cell(v) for v in x] + [""] * (width - len(x)) for x in rows]
        r = c.put(f"{SHEETS}/{sid}/values/A1", params={"valueInputOption": "RAW"}, headers=h, json={"values": values})
        if r.status_code != 200:
            raise SheetsError(f"เขียนข้อมูลลงชีตไม่สำเร็จ ({r.status_code})")
        if share_with:
            # แชร์ไม่สำเร็จไม่ล้มทั้งงาน — ชีตอยู่ใน Shared Drive ของบริษัท คนในทีมเปิดได้อยู่แล้ว
            c.post(f"{DRIVE}/files/{sid}/permissions", headers=h,
                   params={"supportsAllDrives": "true", "sendNotificationEmail": "false"},
                   json={"type": "user", "role": "writer", "emailAddress": share_with})
    return f"https://docs.google.com/spreadsheets/d/{sid}/edit"
