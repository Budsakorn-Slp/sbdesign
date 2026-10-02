"""ความปลอดภัยของ HTML ที่เอาไปใส่หน้าเว็บด้วย innerHTML

มีสองที่ในหน้าเว็บที่ใส่ HTML ดิบลงไป (dangerouslySetInnerHTML):
  InfoPage     body_html ของหน้า CMS
  ProductPage  description_long ของสินค้า

ทั้งคู่ผ่าน html_clean.clean ตอน ETL · ถ้าตัวนี้มีรู แปลว่าใครที่แก้เนื้อหาใน Magento
ได้ (พนักงานใน หรือคนที่แฮกเข้าไปได้) จะรันสคริปต์บนเว็บเราได้ทันที

เทสนี้ยิงรูปแบบโจมตีจริงใส่ ไม่ใช่ตรวจว่าโค้ดหน้าตาถูก — เพราะช่องโหว่ที่เจอมาแล้ว
สองตัวต่างก็ "อ่านโค้ดแล้วดูถูกต้อง" ทั้งคู่
"""
import pytest

from app.etl.html_clean import clean

# คำที่ไม่ควรเหลือรอดออกมาเลย
DANGEROUS = (
    "<script", "javascript:", "vbscript:", "data:text",
    "onerror", "onload", "onclick", "onfocus", "onmouseover",
    "<iframe", "<svg", "<body", "<input", "<object", "<embed",
)

ATTACKS = [
    ("<script>alert(1)</script>ข้อความ", "script ตรงๆ"),
    ("<SCRIPT>alert(1)</SCRIPT>", "ตัวพิมพ์ใหญ่"),
    ('<img src=x onerror="alert(1)">', "event handler"),
    ("<img src=x onerror=alert(1)>", "event handler ไม่มีเครื่องหมายคำพูด"),
    # เบราว์เซอร์ยอมให้ "/" คั่นแทนเว้นวรรค — ตัวกรองที่จับเฉพาะเว้นวรรคจะมองไม่เห็น
    ("<svg/onload=alert(1)>", "ใช้ / คั่นแทนเว้นวรรค"),
    ("<img/onerror=alert(1) src=x>", "/ คั่น + มี src"),
    ('<a href="javascript:alert(1)">ก</a>', "javascript: ใน href"),
    ('<a/href="javascript:alert(1)">ก</a>', "javascript: + / คั่น"),
    ('<a href=" javascript:alert(1)">ก</a>', "เว้นวรรคนำหน้า scheme"),
    ('<a href="java\tscript:alert(1)">ก</a>', "แทรก tab กลาง scheme"),
    ('<a href="vbscript:msgbox(1)">ก</a>', "vbscript:"),
    ('<img src="data:text/html,<script>alert(1)</script>">', "data: url"),
    ('<iframe src="http://evil.com"></iframe>', "iframe"),
    ("<body onload=alert(1)>", "body onload"),
    ("<input onfocus=alert(1) autofocus>", "input autofocus"),
    ('<div style="background:url(javascript:alert(1))">x</div>', "javascript ใน style"),
    ("&lt;script&gt;alert(1)&lt;/script&gt;", "script ที่ถูก escape ไว้"),
    ("<object data='javascript:alert(1)'></object>", "object"),
]


@pytest.mark.parametrize("raw,name", ATTACKS, ids=[a[1] for a in ATTACKS])
def test_กันการฝังสคริปต์(raw, name):
    out = (clean(raw) or "").lower()
    found = [d for d in DANGEROUS if d in out]
    assert not found, f"{name}: หลุด {found} -> {out!r}"


GOOD = [
    ("<p>ข้อความปกติ</p>", "<p>"),
    ('<a href="https://sb.com">ลิงก์นอก</a>', "https://sb.com"),
    ('<a href="/page">ลิงก์ภายใน</a>', "/page"),
    ('<a href="mailto:a@b.com">อีเมล</a>', "mailto:"),
    ("<ul><li>ข้อ 1</li><li>ข้อ 2</li></ul>", "<li>"),
    ("<strong>ตัวหนา</strong>", "<strong>"),
    ("<table><tr><td>ช่อง</td></tr></table>", "<td>"),
]


@pytest.mark.parametrize("raw,must_keep", GOOD, ids=[g[1] for g in GOOD])
def test_เนื้อหาปกติต้องไม่โดนตัด(raw, must_keep):
    assert must_keep in (clean(raw) or ""), f"ตัดของดีทิ้ง: {raw!r} -> {clean(raw)!r}"


def test_รูปที่มี_src_ถูกต้องต้องรอด():
    """เคยมีอักขระ backspace ปนอยู่กลาง regex ทำให้ลบ <img> ทิ้งทุกตัวเงียบๆ

    รูปในหน้า CMS และคำบรรยายสินค้าจึงหายไปหมดโดยไม่มีใครรู้ — อ่านโค้ดก็ดูถูกต้อง
    เพราะอักขระนั้นมองไม่เห็น
    """
    out = clean('<img src="https://cdn.sb.com/x.jpg" alt="รูปสินค้า">')
    assert "cdn.sb.com/x.jpg" in out and "<img" in out


def test_รูปที่ไม่มี_src_ต้องถูกตัด():
    """มาจาก {{media url=...}} ของ Magento ที่แปลไม่ได้ เหลือไว้จะเป็นไอคอนรูปแตก"""
    assert clean('<img alt="ไม่มี src">') == ""


def test_ไฟล์ตัวกรองต้องไม่มีอักขระควบคุมปน():
    """กันบั๊กเดิมกลับมา — อักขระควบคุมใน regex ทำให้เงื่อนไขเพี้ยนโดยที่อ่านโค้ดไม่เห็น"""
    from pathlib import Path

    import app.etl.html_clean as m

    raw = Path(m.__file__).read_bytes()
    bad = [b for b in raw if 1 <= b <= 8 or b in (11, 12) or 14 <= b <= 31]
    assert not bad, f"มีอักขระควบคุมปนอยู่ {len(bad)} ตัว"
