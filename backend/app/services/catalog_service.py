import operator
from datetime import date
from decimal import Decimal
from functools import reduce
from urllib.parse import quote

from sqlalchemy import String, Text, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.integrations.sap.base import MaterialDTO
from app.models.catalog import Brand, Category, Material, MaterialCategory, MaterialPrice, Plant, ProductStock, ProductStockSite
from app.models.common import utcnow
from app.models.user import User
from app.services import search_query as sq


def web_matnr_prefixes() -> tuple[str, ...]:
    return tuple(p.strip() for p in get_settings().catalog_matnr_prefixes.split(",") if p.strip())


def matnr_groups() -> dict[str, str]:
    """ชื่อกลุ่มสินค้า → ตัวขึ้นต้น MATNR (ดู catalog_matnr_groups) เช่น display → 20"""
    out: dict[str, str] = {}
    for pair in get_settings().catalog_matnr_groups.split(","):
        name, _, prefix = pair.partition(":")
        if name.strip() and prefix.strip():
            out[name.strip()] = prefix.strip()
    return out


def is_display_item(matnr: str) -> bool:
    """สินค้าตัวโชว์ไหม — ดูจากตัวขึ้นต้น MATNR (ดู catalog_matnr_groups)

    ตัดสินที่นี่ที่เดียว หน้าเว็บรับมาเป็นธง is_display ไม่ต้องรู้ว่าเลขนำหน้าคืออะไร
    """
    prefix = matnr_groups().get("display")
    return bool(prefix and (matnr or "").startswith(prefix))


def group_of(matnr: str) -> str | None:
    """MATNR นี้อยู่กลุ่มไหน (regular / display / consign) — ดูจากตัวขึ้นต้น"""
    code = matnr or ""
    # เรียงจากตัวขึ้นต้นยาวสุดก่อน เผื่ออนาคตมีกลุ่มที่ใช้เลขนำหน้าซ้อนกัน เช่น 2 กับ 20
    for name, prefix in sorted(matnr_groups().items(), key=lambda kv: -len(kv[1])):
        if code.startswith(prefix):
            return name
    return None


def pickup_only(matnr: str) -> bool:
    """สินค้าชิ้นนี้ยังชำระเงินออนไลน์ไม่ได้ใช่ไหม (ของตัวโชว์/ฝากขาย — ต้องรับที่สาขา)

    ตัดสินที่นี่ที่เดียวจากค่า online_checkout_blocked_groups เพื่อให้วันที่เปิดขายออนไลน์ได้
    แก้ค่าเดียวจบ ไม่ต้องไล่แก้ทั้งตะกร้า/หน้าชำระเงิน/ใบเสนอราคา
    """
    blocked = {g.strip() for g in get_settings().online_checkout_blocked_groups.split(",") if g.strip()}
    if not blocked:
        return False
    return group_of(matnr) in blocked


def is_web_visible(matnr: str) -> bool:
    """สินค้ากลุ่มไหนโชว์บนเว็บได้ — ดูจากตัวขึ้นต้นของ MATNR (ดู catalog_matnr_prefixes)

    ตัดสินที่นี่ที่เดียว แล้วเก็บผลลงธง is_public ตอน import ทุกหน้าที่เช็ค is_public
    อยู่แล้วจึงกรองตามไปเอง ไม่ต้องไล่เติม where ทีละ query (มีจุดที่หลุดง่ายหลายจุด)
    """
    pre = web_matnr_prefixes()
    return not pre or (matnr or "").startswith(pre)


def prices_of(m: Material) -> dict[str, Decimal]:
    today = date.today()
    out: dict[str, Decimal] = {}
    for p in m.prices:
        if (p.valid_from and today < p.valid_from) or (p.valid_to and today > p.valid_to):
            continue
        out[p.tier] = p.price
    return out


def unit_price_for(m: Material, user: User | None) -> tuple[Decimal, str]:
    """ทุกคนเห็นราคาเดียวกัน — ลูกค้าไม่มีระดับสมาชิก สิทธิประโยชน์อยู่ที่แต้มสะสมแทน

    user รับไว้เพื่อให้ผู้เรียกไม่ต้องแก้ตอนวันหลังมีราคาเฉพาะกลุ่ม (เช่น ราคาโครงการ/องค์กร)
    """
    return prices_of(m).get("standard", Decimal(0)), "standard"


def get_material(db: Session, matnr: str) -> Material | None:
    return db.scalar(select(Material).options(selectinload(Material.prices), selectinload(Material.category), selectinload(Material.brand)).where(Material.matnr == matnr))


def descendant_category_ids(db: Session, category_id: str) -> list[str]:
    """ไล่ลงทั้งกิ่ง ไม่ใช่แค่ชั้นเดียว — ต้นไม้หมวดลึก 3 ชั้นแล้ว (กลุ่มเมนู > c3 > c4)
    และสินค้าเกาะอยู่ที่ใบ ถ้าไล่แค่ชั้นเดียวหมวดกลุ่มจะค้นแล้วไม่เจออะไรเลย
    """
    ids = [category_id]
    frontier = [category_id]
    for _ in range(4):  # กันวนไม่รู้จบถ้าข้อมูลหมวดพันกันเอง
        if not frontier:
            break
        frontier = [c for c in db.scalars(select(Category.id).where(Category.parent_id.in_(frontier))) if c not in ids]
        ids += frontier
    return ids


SORTS = ("relevance", "price_asc", "price_desc", "discount", "new", "bestseller")
# keyword = จับคำให้ตรงอย่างเดียว (พิมพ์ "โต๊ะ" ต้องได้โต๊ะทุกตัว) · smart = ตีความประโยคเป็นตัวกรอง
# auto = จับคำก่อน ถ้าไม่เจอค่อยตีความ — ค่าเริ่มต้น เพราะโหมดจับคำแม่นกว่าเมื่อคำค้นสั้น
MODES = ("auto", "keyword", "smart")

# ราคาปกติ/ราคาก่อนลด แยกเป็น subquery ไว้ join — เอาไว้ทั้งกรอง เรียง และหาช่วงราคา
_STD = select(MaterialPrice.matnr, MaterialPrice.price.label("price")).where(MaterialPrice.tier == "standard").subquery()
_CMP = select(MaterialPrice.matnr, MaterialPrice.price.label("compare_at")).where(MaterialPrice.tier == "compare_at").subquery()

# ตัวที่มีรูปขึ้นก่อน — ตอนนี้ต้นทาง Magento มีรูปแค่ ~22% ถ้าเรียงตามชื่อล้วน
# หน้าแรกจะเต็มไปด้วยกล่องเปล่า
_NO_IMAGE = case((or_(Material.image_url.is_(None), Material.image_url == ""), 1), else_=0)

# ของหมดไปอยู่ล่างสุดเสมอ ไม่ว่าจะเรียงแบบไหน
#
# สำคัญกับหน้าพนักงานเป็นพิเศษ: พนักงานเห็นของที่ซ่อนด้วย (include_hidden) ลิสต์จึงมีของหมด
# ปนอยู่เต็มไปหมด ถ้าไม่ดันลงล่าง คนหน้าร้านต้องเลื่อนผ่านของที่ขายไม่ได้ก่อนจะเจอของที่ขายได้
#
# "หมด" = เคยเช็คกับ SAP แล้วเหลือ 0 ทั้งของพร้อมส่งและรอบที่จะเข้า และไม่ใช่สินค้าสั่งทำ
# ตัวที่ยังไม่เคยเช็ค (ไม่มีแถวใน cache) ถือว่ายังไม่รู้ ไม่นับว่าหมด จึงไม่ถูกดันลง
def _sold_out_matnrs():
    """รหัสของที่หมดจริง — นิยามเดียวที่ใช้ทั้งการดันลงล่างและตัวกรอง "เฉพาะของหมด"
    แยกนิยามกันเมื่อไรจะมีวันที่สองที่ให้คำตอบไม่ตรงกันโดยไม่มีใครรู้"""
    return select(ProductStock.matnr).where(
        ProductStock.sap_known.is_(True),
        ProductStock.ready_qty <= 0,
        ProductStock.later_qty <= 0,
        ProductStock.made_to_order.is_(False),
    )


_SOLD_OUT = case((Material.matnr.in_(_sold_out_matnrs()), 1), else_=0)


def _haystack():
    """กองข้อความที่ให้ค้น — รวมชื่อ รหัส รุ่น สเปก แบรนด์ และชื่อหมวดไว้ก้อนเดียว

    ทำแบบนี้เพื่อให้พิมพ์ข้ามฟิลด์ได้ เช่น "koncept เตียง" (แบรนด์ + ชื่อ)
    หรือ "โซฟา 3 ที่นั่ง" ที่คำกระจายอยู่คนละช่อง
    """
    return func.concat_ws(
        " ", Material.name_th, func.coalesce(Material.name_en, ""), func.coalesce(Material.name_raw, ""),
        func.coalesce(Material.variant, ""),
        func.coalesce(Material.spec, ""), func.coalesce(Material.sku, ""), Material.matnr,
        func.coalesce(Material.color, ""), func.coalesce(Material.style, ""),
        func.coalesce(Brand.name, ""), func.coalesce(Category.name_th, ""),
    )


def _like(s: str) -> str:
    """หนี wildcard ที่หลุดมากับคำค้น — normalize ตัด % กับ _ ไปแล้ว เหลือ backslash ที่ต้องกัน"""
    return s.replace("\\", "\\\\")


def _side_fields(pattern: str):
    """คำนี้โผล่ในช่องรองช่องใดช่องหนึ่งไหม — ชื่ออังกฤษ / ชื่อดิบ SAP / ซีรีส์ / สเปก / สี"""
    return or_(
        func.coalesce(Material.name_en, "").ilike(pattern),
        func.coalesce(Material.name_raw, "").ilike(pattern),
        func.coalesce(Material.variant, "").ilike(pattern),
        func.coalesce(Material.spec, "").ilike(pattern),
        func.coalesce(Material.color, "").ilike(pattern),
    )


def _token_clause(t: sq.QueryToken, hay):
    """คำนี้ถือว่า "เข้า" เมื่อตรงคำใดคำหนึ่งในกลุ่มคำพ้อง หรือเข้าครบทุกคำย่อยหลังตัดคำ

    ("โซฟาหนัง" ไม่มีในชื่อสินค้าตัวไหนเลย แต่ "โซฟา" + "หนัง" มีครบในตัวเดียวกัน = เข้า)
    """
    ors = [hay.ilike(f"%{_like(v)}%") for v in t.variants]
    if len(t.segments) > 1:
        ors.append(and_(*[hay.ilike(f"%{_like(s)}%") for s in t.segments]))
    return or_(*ors)


def _code_clause(codes: list[str]):
    """รหัสตรงเป๊ะ / ขึ้นต้นด้วยรหัสนี้ / มีรหัสนี้อยู่ข้างใน

    คนสแกนบาร์โค้ดหรือพิมพ์ MATNR เต็มต้องได้ตัวนั้นเสมอ ส่วนแบบ "มีอยู่ข้างใน" เผื่อเซลล์
    ก๊อปมาไม่ครบหรือจำได้แต่ท้ายรหัส (เช่น 027037 ของ 19027037) — คะแนนความตรงจะดัน
    ตัวที่ตรงเป๊ะขึ้นบนสุดอยู่แล้ว ผลแบบหลวมจึงไม่ไปเบียดตัวที่ใช่
    """
    exact = or_(Material.matnr.in_(codes), Material.sku.in_(codes), func.coalesce(Material.barcode, "").in_(codes))
    partial = [c for c in codes if 4 <= len(c) < 18]
    return or_(exact, *[Material.matnr.like(f"%{c}%") for c in partial]) if partial else exact


def _score(a: sq.AnalyzedQuery):
    """คะแนนความตรง = ผลรวมหลักฐานหลายชั้น ใช้เรียงผลตอนโหมด "แนะนำ"

    รหัสตรงเป๊ะ > ทั้งวลีอยู่ต้นชื่อ > ทั้งวลีอยู่ในชื่อ > รายคำในชื่อ > รายคำในช่องรอง
    ให้แต้มเป็น "ผลรวม" ไม่ใช่ case ชั้นเดียวแบบเดิม เพราะของเดิมพิมพ์หลายคำแล้วทุกตัวได้
    คะแนนพื้น 20 เท่ากันหมด ลำดับจึงไปตกอยู่กับยอดขายแทนความตรง · ตัวขายดี/มีรูปได้แต้มน้อยๆ
    ไว้ตัดสินเฉพาะตอนคะแนนเนื้อหาเสมอกัน
    """
    parts = []
    if a.codes:
        parts.append(case((or_(Material.matnr.in_(a.codes), Material.sku.in_(a.codes),
                               func.coalesce(Material.barcode, "").in_(a.codes)), 1000), else_=0))
        pre = [c for c in a.codes if 4 <= len(c) < 18]
        if pre:
            parts.append(case(
                (or_(*[Material.matnr.like(f"{c}%") for c in pre]), 300),
                (or_(*[Material.matnr.like(f"%{c}%") for c in pre]), 150),
                else_=0,
            ))
    if a.tokens and a.norm:
        phrase = _like(a.norm)
        parts.append(case((Material.name_th.ilike(f"{phrase}%"), 200), (Material.name_th.ilike(f"%{phrase}%"), 120), else_=0))
    for t in a.tokens:
        raw = f"%{_like(t.raw)}%"
        syn = [f"%{_like(v)}%" for v in t.variants]
        parts.append(case(
            (Material.name_th.ilike(raw), 40),
            (or_(*[Material.name_th.ilike(p) for p in syn]), 30),
            (or_(*[_side_fields(p) for p in syn]), 18),
            (or_(func.coalesce(Brand.name, "").ilike(raw), func.coalesce(Category.name_th, "").ilike(raw)), 10),
            else_=0,
        ))
    parts.append(case((Material.is_bestseller.is_(True), 6), else_=0))
    parts.append(case((_NO_IMAGE == 0, 4), else_=0))
    return reduce(operator.add, parts)


def _filtered(db: Session, f: "SearchFilters"):
    """เงื่อนไขร่วมของทั้งผลค้นหาและ facet — join ราคาไว้เสมอ (สินค้า 1 ตัวมีราคาปกติแถวเดียว ไม่บานปลาย)"""
    stmt = (
        select(Material)
        .outerjoin(_STD, _STD.c.matnr == Material.matnr)
        .outerjoin(_CMP, _CMP.c.matnr == Material.matnr)
        .outerjoin(Brand, Brand.id == Material.brand_id)
        .outerjoin(Category, Category.id == Material.category_id)
    )
    a = analysis_of(db, f) if f.q else None
    # ของที่ข้อมูลไม่ครบ (ไม่มีรูป/ไม่มีราคา/ชื่อยังเป็นรหัสโรงงาน) หรือเช็คแล้วของหมด
    # ลูกค้าไม่ควรเห็น แต่เซลล์/แอดมินต้องค้นเจอทุกตัวเสมอ ไม่งั้นเช็คสต็อกให้ลูกค้าหน้าร้านไม่ได้
    # หมวด "สินค้าตัวโชว์" กรองเหมือนกันทั้งลูกค้าและพนักงาน — เอาเฉพาะที่พร้อมขายจริง
    #
    # พนักงานปกติเห็นของที่ซ่อนด้วย (include_hidden) แต่เฉพาะตอน "ค้นหา" เท่านั้น
    # ตอนเปิดดูทั้งหมวดไม่ควรโหลดตัวโชว์มาทั้ง 3,400 ตัว เพราะส่วนใหญ่ยังไม่มีส่วนลดให้ขาย
    # หน้าร้านจะช้าโดยไม่ได้อะไร · ของที่ซ่อนยังค้นด้วยชื่อ/รหัสเจอตามปกติ
    browsing_display = f.group == "display" and not f.q
    if not f.include_hidden or browsing_display:
        stmt = stmt.where(Material.is_public.is_(True))
    if not f.include_hidden:
        # ตัวที่ "เคยเช็ค" กับ SAP แล้วเหลือ 0 ถึงตัดออก — ตัวที่ยังไม่เคยเช็คเลย (ไม่มีแถวใน cache)
        # ถือว่ายังไม่รู้ ไม่ซ่อน
        # ซ่อนเฉพาะตัวที่ "หมดสนิท" — ของหมดแต่มีรอบเข้า หรือสินค้าสั่งทำ ยังสั่งได้ ต้องโชว์
        sold_out = select(ProductStock.matnr).where(
            ProductStock.sap_known.is_(True),
            ProductStock.ready_qty <= 0,
            ProductStock.later_qty <= 0,
            ProductStock.made_to_order.is_(False),
        )
        hide_sold_out = Material.matnr.notin_(sold_out)
        if a and a.codes:
            # พิมพ์รหัสสินค้ามาตรงๆ ต้องเจอแม้ของหมด — ลูกค้าจะได้รู้ว่า "มีรุ่นนี้แต่หมด"
            # ไม่ใช่ "ไม่มีรุ่นนี้" (หน้าเว็บโชว์เป็นการ์ดทึบกดไม่ได้)
            hide_sold_out = or_(_code_clause(a.codes), hide_sold_out)
        stmt = stmt.where(hide_sold_out)
    if f.q and a:
        hay = _haystack()
        # ปกติต้องเข้าครบทุกคำ (แคบแต่แม่น) — ถ้าไม่เจอเลย search() จะสั่งผ่อนเป็น "คำใดคำหนึ่ง" ให้เอง
        parts = [_token_clause(t, hay) for t in a.tokens]
        joined = (or_(*parts) if f.loose else and_(*parts)) if parts else None
        if a.codes:
            # รหัสต้องเจอเสมอ ต่อให้คำอื่นในคิวรีไม่เข้าเงื่อนไข
            code = _code_clause(a.codes)
            stmt = stmt.where(or_(code, joined) if joined is not None else code)
        elif joined is not None:
            stmt = stmt.where(joined)
    if f.category:
        cids = descendant_category_ids(db, f.category)
        # หมวดชุดที่ยกมาจากเว็บจริงเก็บใน material_categories (สินค้าตัวเดียวอยู่ได้หลายหมวด)
        # ส่วนหมวดชุดเดิมจาก SAP อยู่ที่ materials.category_id — ต้องยอมรับทั้งสองทาง
        # ไม่งั้นกดหมวดใหม่จะไม่เจออะไร และกดหมวดเก่าก็จะหายไปด้วย
        linked = select(MaterialCategory.matnr).where(MaterialCategory.category_id.in_(cids))
        stmt = stmt.where(or_(Material.category_id.in_(cids), Material.matnr.in_(linked)))
    if f.room:
        stmt = stmt.where(Material.room == f.room)
    if f.group:
        # กลุ่มสินค้าตัดสินจากตัวขึ้นต้น MATNR (20 = ตัวโชว์) — ต้นทางไม่มีฟิลด์ไหนบอกนอกจากรหัส
        prefix = matnr_groups().get(f.group)
        if prefix:
            stmt = stmt.where(Material.matnr.like(f"{prefix}%"))
    elif not f.include_hidden:
        # สินค้าตัวโชว์ (20) เป็นสินค้ารุ่นเดียวกับตัวปกติ (19) ชื่อ/รูปก๊อปกันมาทั้งดุ้น
        # ถ้าปล่อยขึ้นในผลค้นหาทั่วไปด้วย ลูกค้าจะเห็นของชิ้นเดียวกันสองใบทุกหน้า
        # จึงโผล่เฉพาะตอนขอกลุ่มนี้ตรงๆ (?group=display) · เซลล์ (include_hidden) ยังค้นเจอปกติ
        disp = matnr_groups().get("display")
        if disp:
            stmt = stmt.where(~Material.matnr.like(f"{disp}%"))
    if f.color:
        # ต้นทางเขียนสีไม่เป็นมาตรฐาน ("ขาว" / "สีขาว" / "สีขาว-แดง") จับแบบมีคำนี้อยู่พอ
        stmt = stmt.where(func.coalesce(Material.color, "").ilike(f"%{_like(f.color)}%"))
    if f.tag == "new":
        stmt = stmt.where(Material.is_new.is_(True))
    elif f.tag:
        # cast เป็น Text ไม่ใช่ String — PostgreSQL มี cast json->text แต่ไม่มี json->varchar
        # (SQLite เก็บ JSON เป็นข้อความอยู่แล้วจึงผ่านทั้งสองแบบ ความต่างเลยไม่โผล่ตอน dev)
        stmt = stmt.where(cast(Material.tags, Text).like(f'%"{f.tag}"%'))
    if f.min_price is not None:
        stmt = stmt.where(_STD.c.price >= f.min_price)
    if f.max_price is not None:
        stmt = stmt.where(_STD.c.price <= f.max_price)
    if f.discount_only:
        stmt = stmt.where(_CMP.c.compare_at > _STD.c.price)
    if f.has_image:
        stmt = stmt.where(Material.image_url.isnot(None), Material.image_url != "")
    if f.abc:
        stmt = stmt.where(Material.abc_class == f.abc)
    if f.plant:
        # เลือกสาขาแล้ว = อยากเห็นเฉพาะของที่ไปดู/ไปรับที่สาขานั้นได้จริง
        # อ่านจาก product_stock_sites (ยอดรายสาขาจาก SAP) ไม่ใช่ product_stock ที่เป็นยอดรวม
        stmt = stmt.where(Material.matnr.in_(
            select(ProductStockSite.matnr).where(ProductStockSite.plant_code == f.plant,
                                                 ProductStockSite.available_qty > 0)
        ))
    if f.sold_out:
        # เฉพาะของที่หมดจริง (เงื่อนไขเดียวกับ _SOLD_OUT ที่ใช้ดันลงล่าง)
        #
        # มีไว้เพราะ "ดันลงล่าง" อย่างเดียวไม่พอสำหรับหน้าพนักงาน — ลิสต์พนักงานมี 28,918 ตัว
        # (ลูกค้าเห็น 3,722) ของหมด 974 ตัวจึงไปกองอยู่ท้ายสุด ซึ่งต้องเลื่อนผ่านของอีกสองหมื่น
        # กว่าตัวถึงจะถึง = เห็นไม่ได้จริงในทางปฏิบัติ
        stmt = stmt.where(Material.matnr.in_(_sold_out_matnrs()))
    if f.in_stock:
        # ต้องอ่านจากตารางเดียวกับที่การ์ดใช้โชว์ "มีของ N ชิ้น" (product_stock) — ของเดิมอ่าน
        # stock_cache ซึ่งเป็นยอดรายสาขาของ ZAIBAPI ตัวเก่าที่มีข้อมูลอยู่แค่ 80 รหัส ผลคือกด
        # "มีของพร้อมส่ง" แล้วได้ 0 รายการ ทั้งที่ทุกใบบนหน้าเพิ่งบอกว่ามีของ
        avail = select(ProductStock.matnr).where(ProductStock.ready_qty > 0)
        stmt = stmt.where(Material.matnr.in_(avail))
    return stmt


class SearchFilters:
    """พารามิเตอร์ค้นหาชุดเดียว ส่งต่อระหว่าง API / ผลลัพธ์ / facet โดยไม่ต้องไล่ส่งทีละตัว"""

    __slots__ = ("q", "category", "room", "tag", "brands", "min_price", "max_price", "discount_only", "in_stock", "has_image",
                 "sold_out", "plant", "sort", "loose", "include_hidden", "analysis", "corrected", "color", "mode", "understood", "effective", "group", "seed", "abc")

    def __init__(self, q=None, category=None, room=None, tag=None, brands=None, min_price=None, max_price=None, discount_only=False, in_stock=False, sold_out=False, plant=None, has_image=False, sort="relevance", include_hidden=False, color=None, mode="auto", group=None, seed=None, abc=None):
        self.q, self.category, self.room, self.tag = q, category, room, tag
        self.color = color  # ชื่อสีแบบไม่ต้องตรงเป๊ะ ("ขาว" เข้าได้ทั้ง "สีขาว" และ "ขาว-แดง")
        self.mode = mode if mode in MODES else "auto"
        self.group = group  # กลุ่มสินค้าตามตัวขึ้นต้น MATNR เช่น display = ตัวโชว์
        # ชั้นสินค้าจาก SAP (MAABC) — N = ของเข้าใหม่ · Z = ขายดี · ใช้เป็นตัวกรองตรงๆ ได้
        self.abc = (abc or "").strip().upper() or None
        self.include_hidden = include_hidden  # เฉพาะพนักงาน — เห็นของที่ยังไม่พร้อมขายออนไลน์ด้วย
        self.brands = [b for b in (brands or []) if b]
        self.min_price, self.max_price = min_price, max_price
        self.discount_only, self.in_stock, self.has_image = discount_only, in_stock, has_image
        self.sold_out = sold_out
        self.plant = plant
        self.sort = sort if sort in SORTS else "relevance"
        # เลขสุ่มประจำการเปิดหน้าหนึ่งครั้ง — ใช้สลับลำดับสินค้าตอนเปิดดูเฉยๆ (ไม่ได้ค้นอะไร)
        self.seed = seed
        self.loose = False  # ผ่อนเป็น "เข้าคำใดคำหนึ่ง" — search() เปิดให้เองเมื่อค้นแบบครบทุกคำแล้วไม่เจอ
        self.analysis = None  # ผลตัดคำ/ขยายคำพ้องของ q — วิเคราะห์ครั้งเดียวใช้ทั้ง where/score/facet
        self.corrected = None  # คำที่ระบบแก้ตัวสะกดให้ ถ้าต้องแก้ถึงจะเจอของ (เอาไปบอกลูกค้าบนหน้าเว็บ)
        self.understood = None  # ผลตีความประโยค ถ้ารอบนี้ใช้โหมดตีความ (sq.Interpretation)
        self.effective = None  # ตัวกรองชุดที่ได้ผลจริง — โหมดตีความสร้างชุดใหม่ facet ต้องนับตามชุดนั้น


def analysis_of(db: Session, f: SearchFilters) -> sq.AnalyzedQuery:
    """วิเคราะห์คำค้นครั้งเดียวต่อหนึ่งคำขอ — where, score และ facet ใช้ชุดเดียวกัน"""
    if f.analysis is None or f.analysis.raw != (f.q or ""):
        f.analysis = sq.analyze(db, f.q or "")
    return f.analysis


def _shuffle(seed: int):
    """ลำดับสุ่มที่ "นิ่ง" ภายในหนึ่ง seed — เลื่อนหน้าถัดไปแล้วของต้องไม่ซ้ำและไม่หาย

    สุ่มตรงๆ ด้วย RANDOM() ไม่ได้ เพราะหน้าถัดไปเป็นคนละคำขอ ฐานจะสุ่มลำดับใหม่ทั้งชุด
    ของที่เคยอยู่หน้า 1 จึงเด้งไปโผล่หน้า 3 ได้ กลายเป็นเลื่อนแล้วเจอของซ้ำ/ของหาย
    แทนที่จะสุ่ม เราคำนวณเลขประจำตัวสินค้าจาก (รหัสสินค้า × seed) — seed เดียวกันได้ลำดับเดิมเป๊ะ
    ทุกหน้า พอรีเฟรชหน้าเว็บก็ได้ seed ใหม่ ลำดับทั้งชุดจึงเปลี่ยนไปเลย

    วิธีทำ: ทุกสินค้ามีเลขประจำตัวคงที่ (materials.shuffle_key คิดจากรหัสด้วย crc32 ตอน import)
    เอามาคูณ seed แล้ว mod — seed เดียวกันได้ลำดับเดิมเป๊ะทุกหน้า, seed ใหม่ได้ลำดับใหม่ทั้งชุด

    ทำไมไม่แปลงรหัสสินค้าเป็นตัวเลขสดๆ อย่างที่เคยทำ: ในฐานมีรหัสที่ไม่ใช่ตัวเลข 491 รหัส
    (A017, A534, A761 ...) · SQLite แปลงแล้วได้ 0 เงียบๆ แต่ PostgreSQL ตีกลับทั้ง query
    ด้วย invalid input syntax for type bigint — หน้าแรกจะพังทั้งหน้าทันทีที่ย้ายฐาน
    เก็บเป็นคอลัมน์ int ไว้ก่อนจึงพ้นปัญหา และเรียงเร็วกว่าเพราะมี index

    mod ก่อนคูณเพื่อไม่ให้เลขล้น 64 บิต
    """
    k = Material.shuffle_key
    return ((k % 2147483647) * seed) % 2147483647


def _ordered(stmt, sort: str, a: sq.AnalyzedQuery | None = None, seed: int | None = None):
    """matnr ต่อท้ายทุกแบบเพื่อให้ลำดับนิ่ง ไม่งั้นค่าซ้ำกันแล้วเลื่อนหน้าถัดไปสินค้าจะซ้ำ/หายเอง

    ของหมด (_SOLD_OUT) นำหน้าทุกแบบการเรียง — ของที่ซื้อไม่ได้ไม่ควรกินที่หน้าแรก
    """
    if sort == "relevance" and a and not a.empty:
        # มีคำค้น = เรียงตามความตรงก่อน แล้วค่อยตัวมีรูป/ขายดี ไม่ใช่เรียงตามชื่อเฉยๆ
        return stmt.order_by(_SOLD_OUT, _score(a).desc(), _NO_IMAGE, Material.sold_qty.desc(), Material.matnr)
    if sort == "price_asc":
        return stmt.order_by(_SOLD_OUT, _STD.c.price.asc(), Material.matnr)
    if sort == "price_desc":
        return stmt.order_by(_SOLD_OUT, _STD.c.price.desc(), Material.matnr)
    if sort == "discount":
        return stmt.order_by(_SOLD_OUT, (_CMP.c.compare_at - _STD.c.price).desc().nullslast(), Material.matnr)
    if sort == "new":
        return stmt.order_by(_SOLD_OUT, Material.created_at.desc().nullslast(), Material.matnr)
    if sort == "bestseller":
        # ชั้น Z (MAABC) ขึ้นก่อนเสมอ — เป็นการจัดชั้นจากยอดขายจริงทั้งบริษัท
        # sold_qty เป็นตัวรอง เพราะนับเฉพาะยอดที่สั่งผ่านเว็บ ของขายดีหน้าร้านจะได้ 0
        return stmt.order_by(_SOLD_OUT, Material.is_bestseller.desc(), Material.sold_qty.desc(), _NO_IMAGE, Material.matnr)
    if seed:
        # เปิดดูเฉยๆ ไม่ได้ค้นอะไร: ชั้น Z (MAABC) ขึ้นก่อน ที่เหลือสลับลำดับใหม่ทุกครั้งที่เข้าหน้า
        # เรียงตามชื่อทำให้หน้าแรกเป็นของชุดเดิมตลอดไป ลูกค้าประจำจึงเห็นแต่ของซ้ำๆ
        return stmt.order_by(_SOLD_OUT, Material.is_bestseller.desc(), _NO_IMAGE, _shuffle(seed), Material.matnr)
    return stmt.order_by(_SOLD_OUT, _NO_IMAGE, Material.name_th, Material.matnr)


def search(db: Session, f: SearchFilters, limit: int = 24, offset: int = 0) -> tuple[list[Material], int]:
    """ค้นแบบแคบก่อน แล้วค่อยผ่อนทีละขั้นถ้าไม่เจอ — ดีกว่าโชว์ "ไม่พบสินค้า" ทั้งที่ของมีอยู่

    ขั้นที่ 1 เข้าครบทุกคำ (แม่นที่สุด) · ขั้นที่ 2 เดาว่าพิมพ์ชื่อรุ่นผิดแล้วลองใหม่
    · ขั้นที่ 3 เข้าคำใดคำหนึ่งก็พอ — คะแนนความตรงจะดันตัวที่เข้าหลายคำขึ้นบนให้เอง
    """
    if f.q and f.mode == "smart":
        got = _interpreted(db, f, limit, offset)
        if got:
            return got
    rows, total = _run(db, f, limit, offset)
    if total or not f.q:
        return rows, total
    fixed = sq.analyze(db, f.q, spell=True)
    if fixed.corrected:
        f.analysis = fixed
        rows, total = _run(db, f, limit, offset)
        if total:
            f.corrected = fixed.corrected
            return rows, total
        f.analysis = None
    if f.mode != "keyword":
        got = _interpreted(db, f, limit, offset)
        if got:
            return got
    if not f.loose and len(analysis_of(db, f).tokens) > 1:
        f.loose = True
        rows, total = _run(db, f, limit, offset)
    return rows, total


def _interpreted(db: Session, f: SearchFilters, limit: int, offset: int) -> tuple[list[Material], int] | None:
    """ค้นแบบ "ตีความประโยค" — แปลงคำค้นเป็นตัวกรอง (หมวด/สี/ราคา) แล้วค่อยค้นด้วยคำที่เหลือ

    คืน None เมื่อตีความไม่ออกหรือแปลแล้วยังไม่เจอของ ผู้เรียกจะได้ถอยไปใช้ผลของโหมดจับคำ
    ตัวกรองที่ลูกค้าเลือกเองมาก่อนสิ่งที่ระบบเดาเสมอ — ติ๊กช่วงราคาไว้แล้วประโยคจะไม่มาทับ
    """
    ip = sq.interpret(db, f.q or "")
    if not ip.useful:
        return None
    # ครบทุกเงื่อนไขก่อน ไม่เจอค่อยผ่อนทีละอย่าง — ทิ้งเลขขนาดก่อน (คนพิมพ์ขนาดคร่าวๆ กันเยอะ)
    # แล้วค่อยทิ้งสี · "ตู้เสื้อผ้าสีแดง สูง 180" ที่ไม่มีสีแดงจริง จะได้ตู้เสื้อผ้าสูง 180 แทน
    # ไม่ใช่ผลมั่วจากการค้นแบบเข้าคำใดคำหนึ่ง
    for drop in ((), ("specs",), ("specs", "color")):
        g = SearchFilters(
            q=" ".join(ip.terms + ([] if "specs" in drop else ip.specs)) or None,
            category=f.category or ip.category_id, room=f.room, tag=f.tag, brands=f.brands, group=f.group,
            min_price=f.min_price if f.min_price is not None else ip.min_price,
            max_price=f.max_price if f.max_price is not None else ip.max_price,
            discount_only=f.discount_only, in_stock=f.in_stock, sold_out=f.sold_out, plant=f.plant, has_image=f.has_image, sort=f.sort,
            include_hidden=f.include_hidden, color=f.color or (None if "color" in drop else ip.color), mode="keyword",
        )
        rows, total = _run(db, g, limit, offset)
        if total:
            ip.dropped = list(drop)
            f.understood, f.effective = ip, g
            return rows, total
    return None


def _run(db: Session, f: SearchFilters, limit: int, offset: int) -> tuple[list[Material], int]:
    stmt = _filtered(db, f)
    if f.brands:
        stmt = stmt.where(Material.brand_id.in_(f.brands))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.options(selectinload(Material.prices), selectinload(Material.category), selectinload(Material.brand))
    rows = db.scalars(_ordered(stmt, f.sort, analysis_of(db, f) if f.q else None, f.seed).offset(offset).limit(limit)).all()
    return list(rows), int(total)


def suggest(db: Session, q: str, include_hidden: bool = False, limit: int = 6) -> tuple[list[dict], list[Material]]:
    """คำแนะนำใต้ช่องค้นหาแบบพิมพ์ไปขึ้นไป — คำค้นยอดฮิต + หมวด + แบรนด์ + สินค้าที่ตรงที่สุด

    ตั้งใจให้เบา: ยิงทุกครั้งที่พิมพ์ (หน้าเว็บหน่วงไว้แล้ว) จึงจำกัดจำนวนทุกชั้นและไม่ขอ facet
    คำค้นยอดฮิตมาจากสิ่งที่ลูกค้าจริงเคยพิมพ์แล้ว "เจอของ" เท่านั้น — คำที่ค้นแล้วศูนย์
    ไม่ควรเอามาแนะนำต่อ
    """
    from app.models.analytics import SearchQuery

    norm = sq.normalize(q)
    if not norm:
        return [], []
    like = f"%{_like(norm)}%"
    out: list[dict] = []
    for term, in db.execute(
        select(SearchQuery.q).where(SearchQuery.q.ilike(like), SearchQuery.result_count > 0)
        .group_by(SearchQuery.q).order_by(func.count().desc()).limit(4)
    ).all():
        out.append({"kind": "term", "label": term, "href": f"/search?q={quote(term)}"})
    for cid, name in db.execute(
        select(Category.id, Category.name_th).where(Category.name_th.ilike(like)).order_by(func.length(Category.name_th)).limit(4)
    ).all():
        if not any(o["label"] == name for o in out):
            out.append({"kind": "category", "label": name, "href": f"/search?category={cid}"})
    for bid, name in db.execute(select(Brand.id, Brand.name).where(Brand.name.ilike(like)).limit(3)).all():
        out.append({"kind": "brand", "label": name, "href": f"/search?brand={bid}"})
    rows, _ = search(db, SearchFilters(q=q, include_hidden=include_hidden), limit=limit)
    return out[:8], rows


def brand_covers(db: Session, brand_ids: list[str]) -> dict[str, dict]:
    """รูปหน้าไทล์ของแต่ละแบรนด์ = รูปสินค้าขายดีสุดของแบรนด์นั้นที่ยังขายได้อยู่

    ทำไมใช้รูปสินค้า ไม่ใช้แบนเนอร์จาก sbdesignsquare.com: หน้า exclusive-brands ที่นั่น
    เป็นร้านใน marketplace เกือบทั้งหมด จับคู่กับแบรนด์ที่เราขายจริงได้แค่ 6 จาก 25
    (ตัวใหญ่สุดอย่าง KONCEPT/DISNEYHOME ไม่มีรูป) แถม alt ว่างทุกใบจนเดาชื่อผิดบ่อย
    ส่วนรูปสินค้าเรามีครบทุกแบรนด์อยู่แล้ว และเป็นของแบรนด์นั้นแน่นอน ไม่มีทางสลับกัน

    เลือกจากชุดเดียวกับผลค้นหา (_filtered) รูปที่ขึ้นจึงเป็นของที่กดเข้าไปแล้วเจอจริง
    """
    if not brand_ids:
        return {}
    base = _filtered(db, SearchFilters()).subquery()
    rows = db.execute(
        select(base.c.brand_id, base.c.matnr, base.c.image_url)
        .where(base.c.brand_id.in_(brand_ids), base.c.image_url.isnot(None), base.c.image_url != "")
        .order_by(base.c.brand_id, base.c.is_bestseller.desc(), base.c.sold_qty.desc(), base.c.matnr)
    ).all()
    out: dict[str, dict] = {}
    for bid, matnr, img in rows:  # เรียงมาแล้ว ตัวแรกของแต่ละแบรนด์คือตัวขายดีสุด
        out.setdefault(bid, {"matnr": matnr, "image_url": img})
    return out


def facets(db: Session, f: SearchFilters, brand_limit: int = 60) -> dict:
    """ตัวเลือกที่ยังเลือกได้จริงของผลค้นหาชุดนี้ + จำนวนของแต่ละตัว

    นับแบรนด์โดย "ไม่" ใส่ตัวกรองแบรนด์เข้าไป ไม่งั้นพอเลือกแบรนด์หนึ่งแล้ว
    ตัวเลือกอื่นจะหายหมด กลับไปเลือกแบรนด์อื่นไม่ได้
    """
    f = f.effective or f  # โหมดตีความค้นด้วยตัวกรองอีกชุด — facet ต้องนับจากชุดที่ได้ผลจริง
    base = _filtered(db, f).with_only_columns(Material.brand_id.label("brand_id"), _STD.c.price.label("price")).subquery()
    rows = db.execute(
        select(Brand.id, Brand.name, func.count()).select_from(base).join(Brand, Brand.id == base.c.brand_id).group_by(Brand.id, Brand.name).order_by(func.count().desc(), Brand.name)
    ).all()
    lo, hi = db.execute(select(func.min(base.c.price), func.max(base.c.price))).first() or (None, None)
    chosen = set(f.brands)
    # แบรนด์ที่ผู้ใช้เลือกไว้ต้องอยู่ในลิสต์เสมอ ไม่งั้นติ๊กออกไม่ได้เมื่อมันหลุด top N
    top = [r for r in rows[:brand_limit]] + [r for r in rows[brand_limit:] if r[0] in chosen]
    return {
        "brands": [{"id": bid, "name": name, "count": int(n)} for bid, name, n in top],
        "price_min": float(lo) if lo is not None else None,
        "price_max": float(hi) if hi is not None else None,
    }


def upsert_materials(db: Session, items: list[MaterialDTO]) -> int:
    n = 0
    for dto in items:
        m = db.get(Material, dto.matnr)
        if not m:
            m = Material(matnr=dto.matnr, sku=dto.sku, name_th=dto.name_th)
            db.add(m)
            n += 1
        m.sku = dto.sku
        m.barcode = dto.barcode
        m.name_th = dto.name_th
        m.name_en = dto.name_en
        m.variant = dto.variant
        m.spec = dto.spec
        m.description = dto.description
        m.category_id = dto.category_id
        m.brand_id = dto.brand_id
        m.room = dto.room
        m.image_url = dto.image_url
        m.requires_install = dto.requires_install
        m.is_takeaway_ok = dto.is_takeaway_ok
        m.is_new = dto.is_new
        m.volume_m3 = Decimal(str(dto.volume_m3)) if dto.volume_m3 is not None else None
        m.weight_kg = Decimal(str(dto.weight_kg)) if dto.weight_kg is not None else None
        m.tags = dto.tags
        m.synced_at = utcnow()
        db.flush()
        existing = {p.tier: p for p in db.scalars(select(MaterialPrice).where(MaterialPrice.matnr == m.matnr)).all()}
        for tier, price in dto.prices.items():
            if tier in existing:
                existing[tier].price = Decimal(str(price))
            else:
                db.add(MaterialPrice(matnr=m.matnr, tier=tier, price=Decimal(str(price))))
    db.commit()
    sq.clear_cache()  # คลังคำตัดคำ/ตีความสร้างจากชื่อสินค้า — ของเข้าใหม่แล้วต้องสร้างใหม่
    return n


def upsert_taxonomy(db: Session, categories: list[dict], brands: list[dict]) -> None:
    for c in categories:
        if not db.get(Category, c["id"]):
            db.add(Category(id=c["id"], name_th=c["name_th"], name_en=c.get("name_en"), room=c.get("room"), icon=c.get("icon"), sort=c.get("sort", 0)))
        db.flush()
        for i, ch in enumerate(c.get("children", [])):
            if not db.get(Category, ch["id"]):
                db.add(Category(id=ch["id"], name_th=ch["name_th"], parent_id=c["id"], room=c.get("room"), sort=i))
    for b in brands:
        if not db.get(Brand, b["id"]):
            db.add(Brand(id=b["id"], name=b["name"]))
    db.commit()
    sq.clear_cache()  # ชื่อหมวด/แบรนด์เปลี่ยน = คลังคำเปลี่ยน


def upsert_plants(db: Session, plants: list[dict]) -> None:
    for p in plants:
        row = db.get(Plant, p["plant_code"])
        if not row:
            row = Plant(plant_code=p["plant_code"], name=p["name"], type=p["type"])
            db.add(row)
        row.name = p["name"]
        row.type = p["type"]
        row.zone_codes = p.get("zone_codes")
        row.address = p.get("address")
    db.commit()
