"""ดึงภาพหน้าแรกจาก Magento CMS (10.9.12.67) -> sb_home_media (10.9.11.111) -> home_media (แอป)

    python -m app.etl.sync_home_media            # ใช้หน้า Home page ที่ active ล่าสุด
    python -m app.etl.sync_home_media --page 7735
    python -m app.etl.sync_home_media --dry      # ดูผลอย่างเดียว ไม่เขียนอะไร

ดึง 3 ส่วนจากหน้า Home page ของ Magento:

  hero          แบนเนอร์แคมเปญหลัก (สไลด์ slick แบบ slidesToShow=1) เอาทั้งไฟล์ PC และ MB
  top_category  แถบ TOP CATEGORIES — รูป + ชื่อหมวด
  inspiration   แถบ HOME INSPIRATIONS — รูป + ชื่อคอลเลกชัน
  brand         แถบ EXCLUSIVE BRAND — โลโก้แบรนด์

เดินทางเดียวกับรูปสินค้า: Magento -> ตาราง sb_* บนฐานเว็บ -> import เข้าฐานแอป
ฝั่งฐานเว็บกันของที่คนแก้มือด้วย is_manual เหมือน sb_products_image

หมายเหตุเรื่องการ parse: Magento PageBuilder เก็บบางบล็อกเป็น HTML ที่ escape ซ้อนอยู่ใน
HTML อีกที (`&lt;div ...&gt;`) เลยต้อง unescape ทั้งเอกสารก่อน ถึงจะ regex เจอ tag จริง
"""

from __future__ import annotations

import argparse
import html as _html
import re
import sys
from urllib.parse import quote

from sqlalchemy import bindparam, case, create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.catalog import Brand, Category
from app.models.content import HomeMedia

for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "encoding", "") and _s.encoding.lower() not in ("utf-8", "utf8"):
        _s.reconfigure(encoding="utf-8", errors="replace")

MEDIA_BASE = "https://media.sbdesignsquare.com/media/"
SECTIONS = ("hero", "top_category", "inspiration", "inspire_tab", "brand")
BRANDS_PAGE = "exclusive-brands"  # หน้าปลายทางของปุ่ม SEE MORE BRAND บนหน้าแรก

_MEDIA_RE = re.compile(r"\{\{media url=([^}]+)\}\}")
_TAG_RE = re.compile(r"<[^>]+>")


def _media(url: str) -> str:
    return MEDIA_BASE + url.strip().strip("\"'")


def _plain(s: str) -> str:
    return _html.unescape(_TAG_RE.sub("", s)).replace("\xa0", " ").strip()


def _magento():
    url = get_settings().magento_url
    if not url:
        raise SystemExit("! ไม่ได้ตั้ง MAGENTO_HOST/USER/PASSWORD ใน .env (ฐาน Magento บน 10.9.12.67)")
    return create_engine(url, pool_pre_ping=True)


def _home_identifier(c) -> str:
    """identifier ของหน้าแรกที่เว็บใช้จริง จาก web/default/cms_home_page ('home|7375' -> 'home')"""
    row = c.execute(
        text(
            "SELECT value FROM core_config_data WHERE path = 'web/default/cms_home_page' "
            "AND value <> 'no-route' ORDER BY scope_id LIMIT 1"
        )
    ).first()
    return (row[0].split("|")[0].strip() if row and row[0] else "") or "home"


def load_page(page_id: int | None = None, identifier: str | None = None) -> tuple[dict, str]:
    """อ่าน cms_page มาแบบ unescape แล้ว — ระบุ page_id, identifier หรือไม่ระบุ = หน้าแรก"""
    with _magento().connect() as c:
        if page_id:
            row = c.execute(
                text("SELECT page_id, title, identifier, content FROM cms_page WHERE page_id = :p"),
                {"p": page_id},
            ).first()
        elif identifier:
            row = c.execute(
                text(
                    "SELECT page_id, title, identifier, content FROM cms_page "
                    "WHERE identifier = :i AND is_active = 1 ORDER BY page_id DESC LIMIT 1"
                ),
                {"i": identifier},
            ).first()
        else:
            # หน้าแรกถูก clone ใหม่ทุกแคมเปญ (home-maintheme-aug26, home-6a95... ฯลฯ) และตัวที่
            # page_id ใหม่สุดไม่ใช่ตัวที่เว็บใช้จริงเสมอไป — ถามจากค่าคอนฟิกของ Magento เอง
            row = c.execute(
                text(
                    "SELECT page_id, title, identifier, content FROM cms_page "
                    "WHERE identifier = :i AND is_active = 1 ORDER BY page_id DESC LIMIT 1"
                ),
                {"i": _home_identifier(c)},
            ).first()
    if not row:
        raise SystemExit(f"! ไม่พบหน้า CMS ที่ต้องการ ({page_id or identifier or 'Home page'})")
    meta = {"page_id": int(row[0]), "title": row[1], "identifier": row[2]}
    return meta, _html.unescape(row[3] or "")


def _slick_blocks(h: str) -> list[tuple[str, str]]:
    """คืน (config, เนื้อบล็อก) ของทุก carousel

    ไม่มี parser จะหาปลาย <div> ที่ถูกต้องไม่ได้ ตัดเอาที่ marker ตัวถัดไปแทน —
    ทั้ง data-slick ของ carousel ถัดไป และ data-content-type="row" ของแถวถัดไป
    (ถ้าตัดแค่ data-slick แบนเนอร์จะกินการ์ด HOME INSPIRATIONS ที่อยู่ถัดลงไปมาด้วย)
    """
    marks = [m.start() for m in re.finditer(r"data-slick='|data-content-type=\"row\"", h)]
    out = []
    for m in re.finditer(r"data-slick='([^']*)'", h):
        nxt = [p for p in marks if p > m.end()]
        out.append((m.group(1), h[m.end() : nxt[0] if nxt else len(h)]))
    return out


def parse_hero(h: str) -> list[dict]:
    """แบนเนอร์แคมเปญหลัก — Magento แยกบล็อก PC กับ MB เป็นคนละ carousel ที่รูปเรียงตรงกัน"""
    blocks: list[list[tuple[str, str, str]]] = []
    for cfg, body in _slick_blocks(h):
        if '"slidesToShow":1' not in cfg.replace(" ", ""):
            continue
        got: list[tuple[str, str, str]] = []
        for am in re.finditer(
            r'<a href="([^"]*)"[^>]*>\s*<img[^>]*src="\{\{media url=([^}]+)\}\}"[^>]*alt="([^"]*)"',
            body,
        ):
            # การ์ด HOME INSPIRATIONS ก็เป็น carousel slidesToShow=1 ในเวอร์ชันมือถือ
            # ต่างกันตรงมี <h3> ชื่อคอลเลกชันใต้รูป — แบนเนอร์ไม่มี ตัวอักษรอยู่ในภาพหมดแล้ว
            if "<h3" in body[am.end() : am.end() + 300]:
                continue
            got.append((am.group(1), am.group(2).strip(), am.group(3)))
        if got:
            blocks.append(got)
    # ชื่อไฟล์ฝั่งมือถือไม่ได้ลงท้าย -MB เสมอไป (มี _Mobile- ด้วย) ตัดสินทั้งบล็อกจากเสียงข้างมาก
    def is_mb(b: list[tuple[str, str, str]]) -> bool:
        return sum(bool(re.search(r"-MB|mobile", f, re.I)) for _, f, _ in b) * 2 > len(b)

    desktop = next((b for b in blocks if not is_mb(b)), [])
    mobile = [f for _, f, _ in next((b for b in blocks if is_mb(b)), [])]
    return [
        {
            "label": None,  # ตัวหนังสือของแบนเนอร์อยู่ในภาพอยู่แล้ว ไม่ต้องซ้อนทับ
            "alt": _plain(alt),
            "image": _media(file),
            "image_mb": _media(mobile[i]) if i < len(mobile) else None,
            "source_href": href,
        }
        for i, (href, file, alt) in enumerate(desktop)
    ]


def parse_top_categories(h: str) -> list[dict]:
    """แถบ TOP CATEGORIES — figure > a > img แล้วชื่อหมวดอยู่ในบล็อก text ถัดไป"""
    start = h.find("CATEGORIES</span>")
    if start < 0:
        return []
    end = h.find("SEE MORE CATEGORIES", start)
    region = h[start : end if end > start else start + 30000]
    out = []
    for chunk in region.split("<figure")[1:]:
        am = re.search(r'<a href="([^"]*)"', chunk)
        im = _MEDIA_RE.search(chunk)
        lm = re.search(r"</figure>(.*?)</p>", chunk, re.S)
        if not (im and lm):
            continue
        label = _plain(lm.group(1))
        if not label:
            continue
        out.append({"label": label, "image": _media(im.group(1)), "source_href": am.group(1) if am else ""})
    return out


def parse_inspirations(h: str) -> list[dict]:
    """แถบ HOME INSPIRATIONS — การ์ดละ a > img แล้วชื่อคอลเลกชันอยู่ใน h3 ใต้รูป"""
    start = h.find('<div id="solution-carousel"')
    if start < 0:
        return []
    out = []
    for m in re.finditer(
        r'<a href="([^"]*)"[^>]*>\s*<img[^>]*src="\{\{media url=([^}]+)\}\}"[^>]*alt="([^"]*)"[^>]*/?>\s*'
        r"</a>\s*<div[^>]*>\s*<h3[^>]*>(.*?)</h3>",
        h[start : start + 40000],
        re.S,
    ):
        out.append(
            {
                "label": _plain(m.group(4)),
                "alt": _plain(m.group(3)),
                "image": _media(m.group(2)),
                "source_href": m.group(1),
            }
        )
    return out


SITE_BASE = "https://www.sbdesignsquare.com/"
BLOG_MEDIA = MEDIA_BASE + "amasty/blog/"
_TAB_ITEM_RE = re.compile(r'<div data-content-type="tab-item"[^>]*data-tab-name="([^"]*)"')
_WIDGET_CATS_RE = re.compile(r'amasty_widget_categories="([\d,]+)"')


def _blog_posts(cat_ids: list[int], limit: int) -> list[dict]:
    """โพสต์ล่าสุดของหมวดบล็อก Amasty — status=2 คือเผยแพร่แล้ว (0=ร่าง)

    รูปปกอยู่ที่ media/amasty/blog/<ไฟล์> · ลิงก์บทความใช้ route 'blog' ของ Amasty
    ที่นี่ยังชี้ออกไปเว็บจริง เพราะฝั่งเราไม่มีหน้าบทความ
    """
    if not cat_ids:
        return []
    with _magento().connect() as c:
        rows = c.execute(
            text(
                "SELECT DISTINCT p.post_id, p.title, p.url_key, "
                "COALESCE(NULLIF(p.list_thumbnail, ''), p.post_thumbnail) AS thumb, p.published_at "
                "FROM amasty_blog_posts p JOIN amasty_blog_posts_category pc ON pc.post_id = p.post_id "
                "WHERE pc.category_id IN :ids AND p.status = 2 "
                "AND COALESCE(NULLIF(p.list_thumbnail, ''), p.post_thumbnail) IS NOT NULL "
                "ORDER BY p.published_at DESC LIMIT :n"
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": cat_ids, "n": limit},
        ).all()
    return [
        {
            "label": _plain(r[1] or ""),
            "alt": _plain(r[1] or ""),
            "image": BLOG_MEDIA + quote(r[3].lstrip("/")),
            "source_href": f"{SITE_BASE}blog/{r[2]}" if r[2] else SITE_BASE + "blog",
        }
        for r in rows
    ]


def parse_inspiration_tabs(h: str, posts_per_tab: int = 5) -> list[dict]:
    """บล็อก FIND YOUR INSPIRATION — แท็บละหลายใบ

    แท็บที่วางแบนเนอร์ไว้ตรงๆ เอารูปจากแบนเนอร์ · แท็บที่เป็น widget บล็อก Amasty
    เอาโพสต์ล่าสุดของหมวดที่ widget อ้างถึงมาแทน (หน้าเว็บจริงก็เรนเดอร์แบบนั้น)
    """
    start = h.find("FIND YOUR INSPIRATION")
    if start < 0:
        return []
    region = h[start : start + 40000]
    # หน้าแรกมีบล็อกแท็บมากกว่าหนึ่งชุด — จำนวนหัวข้อใน tabs-navigation ชุดแรกบอกว่าบล็อกนี้มีกี่แท็บ
    nav = re.search(r'<ul[^>]*class="tabs-navigation"(.*?)</ul>', region, re.S)
    n_tabs = len(re.findall(r'<span class="tab-title">', nav.group(1))) if nav else 0
    marks = [(m.start(), _plain(m.group(1))) for m in _TAB_ITEM_RE.finditer(region)][: n_tabs or None]
    if not marks:
        return []
    out: list[dict] = []
    # แท็บสุดท้ายไม่มีแท็บถัดไปมาปิดท้าย ตัดที่แถวถัดไปของ PageBuilder แทน
    # ไม่งั้นจะลากแบนเนอร์ท้ายหน้าเข้ามาด้วย
    after = [m.start() for m in re.finditer(r'data-content-type="row"', region) if m.start() > marks[-1][0]]
    tail = after[0] if after else len(region)
    for i, (pos, name) in enumerate(marks):
        chunk = region[pos : marks[i + 1][0] if i + 1 < len(marks) else tail]
        items: list[dict] = []
        seen: set[str] = set()
        for m in _MEDIA_RE.finditer(chunk):
            file = m.group(1).strip().strip("\"'")
            # PageBuilder วางแบนเนอร์เป็นคู่ PC/มือถือ (ไฟล์เดียวกันต่อท้าย _1) เอาใบเดียวพอ
            key = re.sub(r"_\d+(\.[a-z0-9]+)$", r"\1", file, flags=re.I)
            if key in seen:
                continue
            seen.add(key)
            href = ""
            am = re.search(r'<a href="([^"]*)"[^>]*>(?:(?!</a>).)*$', chunk[: m.start()], re.S)
            if am:
                href = am.group(1)
            items.append({"label": None, "alt": None, "image": _media(file), "source_href": href})
        if len(items) < posts_per_tab:  # แท็บที่เป็น widget บล็อก (หรือแบนเนอร์ไม่พอ) เติมด้วยโพสต์ล่าสุด
            cats = sorted({int(x) for m in _WIDGET_CATS_RE.finditer(chunk) for x in m.group(1).split(",") if x})
            items += _blog_posts(cats, posts_per_tab - len(items))
        for it in items[:posts_per_tab]:
            it["group_key"] = f"tab{i + 1}"
            it["group_label"] = name
            out.append(it)
    return out


def _words(slug: str) -> str:
    slug = re.sub(r"-\d{4,}$", "", slug)  # รหัสผู้ขายต่อท้าย เช่น -110889
    slug = re.sub(r"[-_]?brand$", "", slug, flags=re.I)
    slug = re.sub(r"[-_]?\d+x\d+.*$", "", slug, flags=re.I)  # ขนาดในชื่อไฟล์ เช่น _650x160
    slug = re.sub(r"^https?w*[-_.]*(www)?[-_.]*", "", slug, flags=re.I)  # href ที่เป็น URL ภายนอก
    slug = re.sub(r"^(instagram|facebook|line)[-_.]*(com)?[-_.]*", "", slug, flags=re.I)
    slug = re.sub(r"^\d+[-_]", "", slug)  # รหัสนำหน้า เช่น 112294-tenon
    slug = re.sub(r"[-_]\d{1,2}$", "", slug)  # เลขลำดับไฟล์ท้ายชื่อ เช่น aiko-5
    words = [w for w in re.split(r"[-_.]+", slug) if w]
    return " ".join(w.upper() if w.isupper() or w.lower() == "sb" else w.capitalize() for w in words)


def _brand_label(href: str, image: str) -> str:
    """ป้ายแบรนด์เดาจาก slug ปลายทาง เพราะ alt ของแบนเนอร์บนหน้า exclusive-brands ว่างทุกใบ

    /maison-co-brand                                    -> Maison Co
    /marketplace/seller/collection/shop/La-Z-Boy-110889 -> La Z Boy   (ตัดรหัสผู้ขายท้าย)

    บาง href ลงท้ายด้วยรหัสผู้ขายล้วนๆ (.../shop/112424) เดาชื่อไม่ได้ ใช้ชื่อไฟล์ภาพแทน
    """
    path = re.split(r"[?#]", href)[0].rstrip("/")
    label = _words(path.rsplit("/", 1)[-1])
    if not label or label.replace(" ", "").isdigit():
        stem = re.sub(r"\.[a-z0-9]+$", "", image.rsplit("/", 1)[-1], flags=re.I)
        label = _words(re.sub(r"^(shop[-_]?by[-_]?brand|banner|web[-_]?banner)[-_]?", "", stem, flags=re.I))
    return label or "แบรนด์"


def parse_brands(h: str) -> list[dict]:
    """หน้า exclusive-brands — แบนเนอร์โลโก้แบรนด์ทั้งหน้า (ทั้งแบรนด์ SB และร้านใน marketplace)

    บนหน้าแรกโชว์แค่ 5 แบรนด์แล้วมีปุ่ม SEE MORE BRAND ไปหน้านี้ — เอาจากปลายทางเลยจะได้ครบ
    """
    out: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(r'<a href="([^"]*)"[^>]*>\s*<img[^>]*src="\{\{media url=([^}]+)\}\}"', h):
        href = m.group(1)
        if "{{widget" in href:  # ลิงก์แบบ widget directive แปลงเป็น URL ไม่ได้
            continue
        image = _media(m.group(2))
        label = _brand_label(href, image)
        if label.lower() in seen:  # บางแบรนด์วางซ้ำหลายแถวบนหน้าเดียว
            continue
        seen.add(label.lower())
        out.append({"label": label, "alt": None, "image": image, "source_href": href})
    return out


def collect(h: str, page_id: int, brands_html: str = "") -> list[dict]:
    """รวมทุก section เป็นแถวหน้าตาเดียวกัน — slug ตั้งจากชื่อไฟล์ภาพ จะได้ upsert ลงแถวเดิม"""
    rows: list[dict] = []
    for section, items in (
        ("hero", parse_hero(h)),
        ("top_category", parse_top_categories(h)),
        ("inspiration", parse_inspirations(h)),
        ("inspire_tab", parse_inspiration_tabs(h)),
        ("brand", parse_brands(brands_html) if brands_html else []),
    ):
        for i, it in enumerate(items):
            name = it["image"].rsplit("/", 1)[-1]
            slug = re.sub(r"\.[a-z0-9]+$", "", name, flags=re.I)
            if it.get("group_key"):  # ไฟล์เดียวกันอาจถูกใช้ซ้ำข้ามแท็บ ใส่แท็บนำหน้ากันชนคีย์
                slug = f"{it['group_key']}-{slug}"
            rows.append(
                {
                    "section": section,
                    "slug": slug[:160],
                    "position": i,
                    "group_key": it.get("group_key"),
                    "group_label": it.get("group_label"),
                    "label": it.get("label"),
                    "alt": it.get("alt"),
                    "image_url": it["image"],
                    "image_mb_url": it.get("image_mb"),
                    "source_href": it.get("source_href") or None,
                    "page_id": page_id,
                }
            )
    return rows


UPSERT_SQL = """
INSERT INTO sb_home_media
  (section, slug, position, label, alt, image_url, image_mb_url, source_href, page_id)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
  position     = IF(is_manual = 1, position,     VALUES(position)),
  label        = IF(is_manual = 1, label,        VALUES(label)),
  alt          = IF(is_manual = 1, alt,          VALUES(alt)),
  image_url    = IF(is_manual = 1, image_url,    VALUES(image_url)),
  image_mb_url = IF(is_manual = 1, image_mb_url, VALUES(image_mb_url)),
  source_href  = IF(is_manual = 1, source_href,  VALUES(source_href)),
  page_id      = VALUES(page_id),
  is_active    = 1
"""


def upsert_sbweb(rows: list[dict]) -> None:
    """เขียนลง sb_home_media บนฐานเว็บ แล้วปิด (is_active=0) แถวเก่าของแคมเปญที่ผ่านไปแล้ว

    ไม่ลบทิ้ง เพราะแคมเปญเก่ายังอาจถูกหยิบกลับมาใช้ และ slug คือชื่อไฟล์ ไม่ชนกัน
    """
    # sb_home_media ไม่มีคอลัมน์ group_* — แถวของบล็อกแท็บลงเฉพาะฐานแอป
    rows = [r for r in rows if r["section"] != "inspire_tab"]
    eng = create_engine(get_settings().sbweb_database_url, pool_pre_ping=True)
    with eng.connect() as c:
        raw = c.connection
        cur = raw.cursor()
        cur.executemany(
            UPSERT_SQL,
            [
                (
                    r["section"], r["slug"], r["position"], r["label"], r["alt"],
                    r["image_url"], r["image_mb_url"], r["source_href"], r["page_id"],
                )
                for r in rows
            ],
        )
        keys = {(r["section"], r["slug"]) for r in rows}
        cur.execute("SELECT section, slug FROM sb_home_media WHERE is_active = 1 AND is_manual = 0")
        stale = [k for k in cur.fetchall() if (k[0], k[1]) not in keys]
        if stale:
            cur.executemany(
                "UPDATE sb_home_media SET is_active = 0 WHERE section = %s AND slug = %s", stale
            )
        raw.commit()
        print(f"  sb_home_media: upsert {len(rows)} แถว" + (f" · ปิดของเก่า {len(stale)}" if stale else ""))


# คำต่อท้ายชื่อแบนเนอร์ที่ไม่ใช่ชื่อสินค้า — ติดไปด้วยแล้วผลค้นหาบานเกินจริง
# ("Tomo Collection" ได้ 66 รายการ ทั้งที่ของรุ่น Tomo มีจริง 35 เพราะคำว่า Collection
#  ไปแมตช์สินค้าตัวอื่นที่ไม่เกี่ยว)
# คำห้อยท้ายชื่อแบนเนอร์ที่ไม่ใช่ชื่อสินค้า — ติดไปด้วยแล้วผลค้นหาบานเกินจริง
_NOISE_WORDS = {"collection", "series", "brand"}


def _clean_label(label: str) -> str:
    """ตัดคำห้อยออกจากชื่อแบนเนอร์ — "Tomo Collection" -> "Tomo"

    ค้นด้วยชื่อเต็มจะได้ของเกินจริง (Tomo Collection ได้ 66 รายการ ทั้งที่รุ่น Tomo
    มีจริง 35 เพราะคำว่า Collection ไปแมตช์สินค้าตัวอื่นที่ไม่เกี่ยว)
    """
    return " ".join(w for w in label.split() if w.lower() not in _NOISE_WORDS)


def _brand_id(db: Session, label: str) -> str | None:
    """ชื่อบนแบนเนอร์ตรงกับแบรนด์ไหนไหม — เทียบแบบไม่สนตัวพิมพ์/ช่องว่าง/จุด

    "Maison&co" บนแบนเนอร์ = "MAISON&CO." ในฐาน · "Sofa Solutions" = "SOFA SOLUTIONS"
    """
    key = re.sub(r"[^a-z0-9&]", "", label.lower())
    if not key:
        return None
    for bid, name in db.execute(select(Brand.id, Brand.name)).all():
        if re.sub(r"[^a-z0-9&]", "", (name or "").lower()) == key:
            return bid
    return None


# ป้ายบนการ์ดหน้าแรกที่เรียกชื่อไม่เหมือนชื่อหมวดของเรา — จับคู่ตรงๆ ไว้ ไม่ปล่อยให้เดาเอง
# ("รีไคลเนอร์" กับ "เก้าอี้พักผ่อน" คือของอย่างเดียวกัน แต่ไม่มีคำไหนซ้อนกันเลย)
ALIASES = {
    "รีไคลเนอร์": "เก้าอี้พักผ่อน",
    "ห้องอาหาร": "ห้องทานอาหาร",
}


def _best_category(db: Session, label: str) -> str | None:
    """หาหมวดที่ตรงกับป้ายบนการ์ดหน้าแรกที่สุด และต้องมีสินค้าจริง

    เงื่อนไขสำคัญคือ "มีของ" — ของเดิมจับได้หมวดที่ชื่อตรงแต่ว่างเปล่า (รีไคลเนอร์ -> slug
    เก่าที่ไม่มีสินค้าสักตัว) ลูกค้ากดจากหน้าแรกแล้วเจอหน้าว่าง ซึ่งแย่กว่าไม่มีการ์ดนั้นเลย

    ลำดับการเลือก: ชื่อตรงเป๊ะ (ชุดเว็บก่อน) -> ชื่อที่ครอบกันได้ (ป้ายอยู่ในชื่อหมวด หรือกลับกัน)
    เอาหมวดที่มีของเยอะสุด เพราะการ์ดหน้าแรกควรพาไปที่กว้างไว้ก่อน ไม่ใช่หมวดย่อยแคบๆ
    """
    # ใช้ TRUE ไม่ใช่ 1 — PostgreSQL ไม่ยอมเทียบคอลัมน์ boolean กับตัวเลข
    # (SQLite เก็บ boolean เป็น 0/1 จึงผ่านทั้งสองแบบ ความต่างเลยไม่โผล่ตอน dev)
    rows = db.execute(text("""
        SELECT c.id, c.name_th, c.source, COUNT(DISTINCT mc.matnr) AS n
        FROM categories c
        LEFT JOIN material_categories mc ON mc.category_id = c.id
        LEFT JOIN materials m ON m.matnr = mc.matnr AND m.is_public = TRUE
        GROUP BY c.id, c.name_th, c.source
    """)).all()
    # หมวดชุด SAP ผูกสินค้าไว้ที่ materials.category_id ไม่ใช่ตารางเชื่อม ต้องนับแยก
    sap = dict(db.execute(text("""
        SELECT category_id, COUNT(*) FROM materials
        WHERE is_public = TRUE AND category_id IS NOT NULL GROUP BY category_id
    """)).all())

    def count(cid: str, n: int) -> int:
        return max(n or 0, sap.get(cid, 0))

    live = [(cid, name or "", src, count(cid, n)) for cid, name, src, n in rows if count(cid, n) > 0]
    label = ALIASES.get(label, label)
    exact = [r for r in live if r[1] == label]
    if exact:
        exact.sort(key=lambda r: (0 if r[2] == "web" else 1, -r[3]))
        return exact[0][0]
    near = [r for r in live if r[2] == "web" and r[1] and (r[1] in label or label in r[1])]
    if near:
        near.sort(key=lambda r: -r[3])
        return near[0][0]
    return None


def _app_href(db: Session, section: str, label: str | None, source_href: str | None) -> str:
    """แปลงลิงก์ปลายทางของ sbdesignsquare.com เป็นเส้นทางในแอปเรา

    หมวดใน CMS เป็น URL path ของ Magento (/furniture/bedroom-furniture/beds) ซึ่งคนละชุด
    กับ category ของเรา (มาจาก SAP) — จับคู่ด้วยชื่อไทยแทน ที่จับไม่ได้ก็ส่งเข้าค้นหา

    แบนเนอร์แบรนด์/คอลเลกชันบนหน้าแรกจะพยายามส่งไปที่ตัวกรองแบรนด์ก่อน เพราะได้ของ
    ครบและตรงกว่าการค้นด้วยข้อความ · ตัวที่ไม่ใช่แบรนด์ (เป็นชื่อรุ่น เช่น Tomo/Trixx)
    ยังต้องใช้ค้นข้อความอยู่ แต่ตัดคำห้อยอย่าง "Collection" ทิ้งก่อนจะได้ไม่กวาดของอื่นมา
    """
    if section == "top_category" and label:
        cid = _best_category(db, label)
        if cid:
            return f"/search?category={cid}"

    if label:
        name = _clean_label(label)
        bid = _brand_id(db, name) or _brand_id(db, label)
        if bid:
            return f"/search?brand={quote(bid)}"
        if name:
            return f"/search?q={quote(name)}"
    m = re.search(r"[?&]q=([^&]+)", source_href or "")
    if m:
        return f"/search?q={m.group(1)}"
    return "/search"


def import_app(db: Session, rows: list[dict]) -> None:
    """ยกลงฐานแอป — ลบทั้งตารางแล้วใส่ใหม่ ของแค่หลักสิบแถว ไม่ต้อง diff ให้ซับซ้อน"""
    db.query(HomeMedia).delete()
    for r in rows:
        db.add(
            HomeMedia(
                section=r["section"],
                slug=r["slug"],
                position=r["position"],
                label=r["label"],
                alt=r["alt"],
                image_url=r["image_url"],
                image_mb_url=r["image_mb_url"],
                source_href=r["source_href"],
                group_key=r.get("group_key"),
                group_label=r.get("group_label"),
                # บทความ/แบนเนอร์ในบล็อกแท็บไม่มีหน้าคู่กันในแอปเรา ลิงก์ออกเว็บจริงไปเลย
                href=r["source_href"] if r["section"] == "inspire_tab" else _app_href(db, r["section"], r["label"], r["source_href"]),
            )
        )
    db.commit()
    print(f"  home_media (ฐานแอป): {len(rows)} แถว")


def main() -> int:
    ap = argparse.ArgumentParser(description="ดึงภาพหน้าแรกจาก Magento CMS -> sb_home_media -> home_media")
    ap.add_argument("--page", type=int, default=None, help="ระบุ page_id เอง (ปกติเลือก Home page active ล่าสุดให้)")
    ap.add_argument("--dry", action="store_true", help="แสดงผลอย่างเดียว ไม่เขียนอะไร")
    ap.add_argument("--no-sbweb", action="store_true", help="ข้ามการเขียนฐานเว็บ ลงเฉพาะฐานแอป")
    args = ap.parse_args()

    meta, h = load_page(args.page)
    brand_meta, brand_html = load_page(identifier=BRANDS_PAGE)
    rows = collect(h, meta["page_id"], brand_html)
    print(f"หน้า {meta['page_id']} · {meta['identifier']} + {brand_meta['page_id']} · {brand_meta['identifier']}")
    for section in SECTIONS:
        got = [r for r in rows if r["section"] == section]
        print(f"  {section}: {len(got)}")
        for r in got:
            print(f"    {r['position']:>2} {r['label'] or r['alt'] or '-'} · {r['slug']}")

    if not any(r["section"] == "hero" for r in rows):
        print("! ไม่เจอแบนเนอร์แคมเปญหลัก — โครง PageBuilder อาจเปลี่ยน ไม่เขียนทับของเดิม", file=sys.stderr)
        return 1
    if args.dry:
        print("(--dry ไม่เขียนอะไร)")
        return 0

    if not args.no_sbweb:
        upsert_sbweb(rows)
    with SessionLocal() as db:
        import_app(db, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
