"""ตัวคุยกับ backend ของเราเอง (HTTP) ให้ MCP server เรียกใช้

ตั้งใจให้ MCP ไม่แตะฐานข้อมูลตรงๆ แต่เรียกผ่าน API ตัวเดียวกับที่หน้าเว็บใช้
กฎธุรกิจทั้งหมด (สิทธิ์ ราคา ส่วนลด เช็คสต็อกทั้งบิล ออกเอกสาร) จึงเป็นชุดเดียวกัน
ไม่มีทางที่ Claude จะออกใบเสนอราคาด้วยเส้นทางที่หน้าเว็บทำไม่ได้
"""
import os
from typing import Any

import httpx


class ApiError(RuntimeError):
    pass


class Api:
    """ล็อกอินด้วยรหัสพนักงานจาก env แล้วถือ access token ไว้ · หมดอายุแล้วล็อกอินใหม่เอง"""

    def __init__(self) -> None:
        self.base = os.environ.get("SB_API_BASE", "http://localhost:8000").rstrip("/")
        self.staff_code = os.environ.get("SB_MCP_STAFF_CODE", "")
        self.password = os.environ.get("SB_MCP_STAFF_PASSWORD", "")
        self.timeout = float(os.environ.get("SB_MCP_TIMEOUT", "60"))
        self._token: str | None = None
        self._me: dict | None = None

    # ---------- auth ----------
    def login(self) -> dict:
        if not self.staff_code or not self.password:
            raise ApiError("ยังไม่ได้ตั้ง SB_MCP_STAFF_CODE / SB_MCP_STAFF_PASSWORD ให้ MCP server")
        r = httpx.post(
            f"{self.base}/auth/login",
            json={"identifier": self.staff_code, "password": self.password, "account_type": "staff"},
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise ApiError(f"ล็อกอินไม่ผ่าน ({r.status_code}) — ตรวจรหัสพนักงาน/รหัสผ่านใน env")
        data = r.json()
        self._token = data["access_token"]
        self._me = data["user"]
        if self._me.get("role") not in ("sales", "manager"):
            raise ApiError(f"บัญชีนี้เป็น {self._me.get('role')} — MCP ต้องใช้บัญชีเซลล์หรือผู้จัดการ")
        return self._me

    @property
    def me(self) -> dict:
        if self._me is None:
            self.login()
        return self._me or {}

    # ---------- คำขอทั่วไป ----------
    def call(self, method: str, path: str, *, json: Any = None, params: dict | None = None, retry: bool = True) -> Any:
        if self._token is None:
            self.login()
        r = httpx.request(
            method, f"{self.base}{path}", json=json, params=params,
            headers={"Authorization": f"Bearer {self._token}"}, timeout=self.timeout,
        )
        if r.status_code == 401 and retry:  # token หมดอายุระหว่างคุย — ต่อให้ใหม่แล้วยิงซ้ำ
            self._token = None
            return self.call(method, path, json=json, params=params, retry=False)
        if r.status_code >= 400:
            raise ApiError(f"{method} {path} -> {r.status_code}: {_detail(r)}")
        if r.status_code == 204 or not r.content:
            return None
        return r.json()

    def get(self, path: str, **params) -> Any:
        return self.call("GET", path, params={k: v for k, v in params.items() if v is not None})

    def post(self, path: str, body: Any = None) -> Any:
        return self.call("POST", path, json=body)

    def delete(self, path: str) -> Any:
        return self.call("DELETE", path)


def _detail(r: httpx.Response) -> str:
    try:
        d = r.json().get("detail")
    except Exception:
        return r.text[:300]
    if isinstance(d, dict):
        return str(d.get("message") or d)
    return str(d or r.text[:300])
