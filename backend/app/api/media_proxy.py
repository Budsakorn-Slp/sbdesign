"""ส่งต่อรูปสินค้าจากเว็บหลักของ SB — ให้หน้าเว็บวาดรูปลงไฟล์ PDF ได้

เว็บหลัก (sbdesignsquare.com) ไม่ส่ง header CORS มา เบราว์เซอร์จึงไม่ยอมให้เอารูปไปวาดลง canvas
(ตอนสร้าง PDF) ดึงผ่านเซิร์ฟเวอร์เรา = รูปมาจากโดเมนเดียวกัน วาดได้

กันใช้เป็นทางยิงไปที่อื่น (SSRF):
  - https เท่านั้น · โฮสต์ต้องอยู่ในรายชื่อตรงตัว (ไม่ใช่ลงท้ายด้วย)
  - ไม่ตามการ redirect · รับเฉพาะ content-type รูป · จำกัดขนาด
"""
from __future__ import annotations

from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

router = APIRouter(tags=["media"])

ALLOWED_HOSTS = {"sbdesignsquare.com", "www.sbdesignsquare.com", "media.sbdesignsquare.com"}
MAX_BYTES = 5 * 1024 * 1024


def _client() -> httpx.Client:
    return httpx.Client(timeout=10.0, follow_redirects=False)


@router.get("/media-proxy")
def media_proxy(url: str = Query(min_length=8, max_length=1000)):
    u = urlparse(url)
    if u.scheme != "https" or (u.hostname or "").lower() not in ALLOWED_HOSTS or u.username or u.password or u.port not in (None, 443):
        raise HTTPException(status_code=400, detail="ไม่อนุญาตที่อยู่รูปนี้")
    try:
        with _client() as c:
            r = c.get(url)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="ดึงรูปไม่สำเร็จ")
    ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
    if r.status_code != 200 or not ctype.startswith("image/") or ctype == "image/svg+xml":
        raise HTTPException(status_code=404, detail="ไม่พบรูป")
    if len(r.content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="รูปใหญ่เกินไป")
    return Response(r.content, media_type=ctype, headers={"Cache-Control": "public, max-age=86400"})
