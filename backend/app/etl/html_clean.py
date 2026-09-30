"""ล้าง HTML จาก CMS ของเว็บจริงให้เหลือแต่เนื้อหา — ใช้กับ etl/sync_cms_pages.py

สองงานคนละเรื่องที่ทำพร้อมกัน:

1. ความปลอดภัย — เนื้อหามาจาก CMS ของบริษัทเองก็จริง แต่หน้าเราเอาไปใส่ด้วย innerHTML
   ถ้ามีใครฝัง script ไว้ (ตั้งใจหรือโดนแฮก) มันจะรันบนเว็บเราด้วย จึงตัด
   script/style/iframe กับ event handler (onclick=...) ทิ้งทุกครั้ง ไม่เชื่อว่าต้นทางสะอาดเสมอ

2. หน้าตา — หน้า CMS สร้างด้วย Magento PageBuilder ซึ่งฝัง style/class/data-* มาเต็ม
   (สีพื้น ระยะห่าง กริด) ถ้าเอามาทั้งดุ้น หน้าเราจะกลายเป็นหน้าตาเว็บเขาปนเว็บเรา
   ตัดออกให้หมดแล้วปล่อยให้ CSS ขาวดำของเราจัดเอง
"""
from __future__ import annotations

import re

# ---------- ตัดทิ้งทั้งก้อน ----------
_DROP_TAGS = re.compile(r"<(script|style|iframe|noscript)\b[^>]*>.*?</\1>", re.I | re.S)
_DROP_OPEN = re.compile(r"<(script|style|iframe|noscript)\b[^>]*>", re.I)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
# บางหน้าใน CMS เก็บ <style>/<script> ไว้แบบ escape (&lt;style&gt;) ซึ่งไม่ใช่แท็กจริง
# ตัวกรองแท็กจึงมองไม่เห็น แล้วมันไปโผล่เป็นข้อความ CSS ดิบกลางหน้า (เจอที่ care-instruction)
_ESCAPED_STYLE = re.compile(r"&lt;style\b.*?&lt;/style&gt;", re.I | re.S)
_ESCAPED_SCRIPT = re.compile(r"&lt;script\b.*?&lt;/script&gt;", re.I | re.S)
# แท็กอื่นที่ถูก escape ไว้ (&lt;img ...&gt;) — CMS ไม่ได้ตั้งใจให้โชว์เป็นข้อความ
# มันคือ markup ที่พังตั้งแต่ต้นทาง ปล่อยไว้จะเห็นเป็นโค้ดดิบกลางหน้า จึงตัดทิ้ง
_ESCAPED_TAG = re.compile(r"&lt;/?[a-zA-Z][^&]{0,400}?&gt;")
_WIDGET = re.compile(r"\{\{[^}]*\}\}")  # directive ของ Magento ({{media url=...}}) แปลไม่ได้นอกระบบมัน
_ON_ATTR = re.compile(r"""\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""", re.I)
_JS_URL = re.compile(r"""\s(href|src)\s*=\s*(["'])\s*javascript:[^"']*\2""", re.I)

# ---------- เหลือไว้ ----------
# แท็กที่เล่าเนื้อหาได้ครบโดยไม่พาสไตล์ของเว็บอื่นติดมา
KEEP_TAGS = {
    "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "strong", "b", "em", "i", "u", "a", "img",
    "table", "thead", "tbody", "tr", "th", "td", "blockquote",
}
# attribute ที่เก็บไว้ต่อแท็ก — ที่เหลือทิ้งหมด (style/class/data-* ของ PageBuilder)
KEEP_ATTRS = {"a": {"href", "target", "rel"}, "img": {"src", "alt"}}

_TAG = re.compile(
    r"""<(/?)([a-zA-Z][\w-]*)((?:\s+[^\s=/>]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?)*)\s*(/?)>"""
)
_ATTR = re.compile(r"""([^\s=/>]+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s>]+))?""")


def _rewrite_tag(m: re.Match) -> str:
    closing, tag, attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
    if tag not in KEEP_TAGS:
        # ถอดเฉพาะตัวแท็ก ไม่ลบข้อความข้างใน (unwrap) — ไม่งั้น div ชั้นนอกของ
        # PageBuilder หายทีเดียวเนื้อหาหายหมดทั้งหน้า
        return ""
    if closing:
        return f"</{tag}>"
    keep = KEEP_ATTRS.get(tag, set())
    out = []
    if keep:
        for am in _ATTR.finditer(attrs or ""):
            name, val = am.group(1).lower(), am.group(2)
            if name in keep and val:
                out.append(f"{name}={val}")
    body = (" " + " ".join(out)) if out else ""
    return f"<{tag}{body}{' /' if selfclose else ''}>"


def drop_leading_heading(html_text: str) -> str:
    """ตัดหัวข้อตัวแรกของเนื้อหาทิ้ง เพราะซ้ำกับชื่อหน้าที่เราวาดเองอยู่แล้ว

    ทุกหน้าใน CMS ขึ้นต้นด้วยหัวข้อที่พูดเรื่องเดียวกับชื่อหน้า — บางหน้าคำเดียวกันเป๊ะ
    ("วิธีการสั่งซื้อสินค้า") บางหน้าใช้คำต่างกันนิดหน่อย ("ร่วมธุรกิจกับเรา" กับ
    "ร่วมทำธุรกิจกับเรา") ถ้าเทียบข้อความแล้วตัดเฉพาะตัวที่เหมือนเป๊ะจะพลาดหน้าหลัง
    จึงตัดหัวข้อแรกทิ้งเสมอ รวมถึงเส้นคั่นที่ตามมาติดๆ ซึ่งเคยเป็นเส้นใต้หัวข้อนั้น
    """
    h = re.sub(r"^\s*<h[1-6]>.*?</h[1-6]>", "", html_text, count=1, flags=re.S | re.I)
    h = re.sub(r"^(\s*<hr\s*/?>)+", "", h, flags=re.I)
    return h.strip()


def clean(raw: str, base_url: str = "") -> str:
    """คืน HTML ที่ปลอดภัยและไม่มีสไตล์ติดมา"""
    h = _ESCAPED_STYLE.sub("", raw or "")
    h = _ESCAPED_SCRIPT.sub("", h)
    h = _ESCAPED_TAG.sub("", h)
    h = _COMMENT.sub("", h)
    h = _DROP_TAGS.sub("", h)
    h = _DROP_OPEN.sub("", h)  # แท็กเปิดที่ไม่มีตัวปิดคู่กัน
    h = _ON_ATTR.sub("", h)
    h = _JS_URL.sub("", h)
    h = _WIDGET.sub("", h)
    if base_url:
        # ลิงก์ในเนื้อหาชี้กันเองด้วย path สั้น — เติมโดเมนเว็บจริงให้ กดแล้วไปถึงของจริง
        h = re.sub(r'href="/(?!/)', f'href="{base_url}', h)
    h = _TAG.sub(_rewrite_tag, h)
    # รูปที่ src ว่าง — มาจาก {{media url=...}} ที่เพิ่งตัดทิ้ง เหลือไว้จะเป็นไอคอนรูปแตก
    h = re.sub(r"<img(?![^>]*src=\"[^\"]+\")[^>]*>", "", h, flags=re.I)
    # h1 ในเนื้อหาจะไปซ้ำกับหัวข้อหน้าที่เราวาดเอง — ลดชั้นลงมาเป็น h2
    h = re.sub(r"<(/?)h1>", r"<\g<1>h2>", h, flags=re.I)
    h = re.sub(r"(<p>\s*</p>\s*)+", "", h)
    h = re.sub(r"[ \t]+", " ", h)
    h = re.sub(r"(\s*\n\s*){3,}", "\n\n", h)
    return drop_leading_heading(h)
