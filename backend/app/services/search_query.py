"""เตรียมคำค้นก่อนส่งเข้า SQL — ตัดคำไทย · คำพ้อง · รหัสสินค้า · เดาคำที่พิมพ์ผิด

ระบบยังค้นด้วย LIKE บนฐานเดียวกับข้อมูล (ไม่มี search engine แยก) งานที่ปกติเป็นหน้าที่ของ
analyzer ในเอนจิน — ตัดคำภาษาไทย, คำพ้อง, ทนคำพิมพ์ผิด — จึงต้องมาทำที่ชั้นนี้แทน แยกเป็น
โมดูลเดี่ยวไว้เพื่อให้วันที่ย้ายไป Postgres FTS หรือ Meilisearch แก้ที่เดียว (ดู docs/search.md)

หัวใจคือ "ภาษาไทยไม่เว้นวรรค" — ลูกค้าพิมพ์ "โซฟาหนัง" แต่ในฐานชื่อว่า "โซฟาเบดหนัง แบบ Zeal"
ค้น LIKE '%โซฟาหนัง%' ตรงๆ จะไม่เจอ ต้องตัดเป็น "โซฟา" + "หนัง" ก่อนถึงจะเจอ
"""
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import get_close_matches
from time import monotonic

from sqlalchemy import select
from sqlalchemy.orm import Session

THAI_LO, THAI_HI = "฀", "๿"
_THAI_RANGE = f"{THAI_LO}-{THAI_HI}"
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
# อะไรที่ไม่ใช่ตัวอักษร/ตัวเลข = ตัวคั่น (คนพิมพ์ขีด ทับ จุด ปนมากับรหัสและชื่อรุ่นตลอด)
_PUNCT = re.compile(r"[^\w" + _THAI_RANGE + r"]+", re.UNICODE)
# ตัดคำตามชนิดอักษร — "sofa3ที่นั่ง" ต้องได้ sofa / 3 / ที่นั่ง ทั้งที่ไม่มีช่องว่างเลย
_RUNS = re.compile(r"[0-9]+|[a-zA-Z]+|[" + _THAI_RANGE + r"]+")
_CODE = re.compile(r"^[0-9]{4,18}$")

MAX_TOKENS = 6  # กันคนวางทั้งย่อหน้ามาแล้วคิวรียาวเกินจำเป็น

# คำที่หมายถึงของอย่างเดียวกันแต่คนพิมพ์คนละแบบ — ไทย/อังกฤษ, คำเรียกติดปาก, ที่สะกดผิดบ่อย
# ทุกคำในกลุ่มเดียวกันใช้แทนกันได้หมด · ต้องมีคำที่ "อยู่ในชื่อสินค้าจริง" อยู่ในกลุ่มด้วยเสมอ
# ไม่งั้นขยายคำไปแล้วก็ไม่มีอะไรให้แมตช์
_SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("โซฟา", "sofa", "couch", "โซฟ่า"),
    ("โซฟาเบด", "sofabed", "โซฟาปรับนอน"),
    ("เตียง", "เตียงนอน", "bed"),
    ("ที่นอน", "ฟูก", "mattress"),
    ("ตู้เสื้อผ้า", "wardrobe", "closet", "ตู้เสือผ้า"),
    ("ตู้", "cabinet", "cupboard"),
    ("ตู้รองเท้า", "ชั้นวางรองเท้า"),
    ("ชั้นวาง", "shelf", "shelves", "rack"),
    ("ชั้นหนังสือ", "bookcase", "bookshelf", "ตู้หนังสือ"),
    ("โต๊ะ", "table", "โตะ"),
    ("โต๊ะทำงาน", "desk", "โต๊ะคอม"),
    ("โต๊ะกลาง", "coffee table"),
    ("โต๊ะทานอาหาร", "โต๊ะอาหาร", "โต๊ะกินข้าว"),
    ("โต๊ะเครื่องแป้ง", "dresser", "vanity"),
    ("เก้าอี้", "chair", "เกาอี้", "เก้าอี"),
    ("เก้าอี้สำนักงาน", "เก้าอี้ทำงาน"),
    ("ชุดวางทีวี", "ที่วางทีวี", "ตู้วางทีวี"),
    ("ทีวี", "tv", "โทรทัศน์"),
    ("โคมไฟ", "lamp", "light"),
    ("พรม", "rug", "carpet"),
    ("ผ้าม่าน", "ม่าน", "curtain"),
    ("หมอน", "pillow", "cushion"),
    ("เครื่องนอน", "bedding", "ผ้าปูที่นอน", "bedsheet"),
    ("กระจก", "mirror"),
    ("ลิ้นชัก", "drawer"),
    ("หนัง", "leather"),
    ("ผ้า", "fabric"),
    ("ไม้", "wood", "wooden"),
    ("เหล็ก", "steel", "metal", "โลหะ"),
    ("ห้องนอน", "bedroom"),
    ("ห้องรับแขก", "ห้องนั่งเล่น", "living"),
    ("ครัว", "kitchen", "ห้องครัว"),
    ("สำนักงาน", "office", "ออฟฟิศ"),
    ("ขาว", "white"), ("ดำ", "black"), ("เทา", "grey", "gray"),
    ("น้ำตาล", "brown"), ("ครีม", "cream"), ("แดง", "red"),
    ("เขียว", "green"), ("ฟ้า", "blue"), ("น้ำเงิน", "navy"),
    ("เบจ", "beige"), ("ทอง", "gold"), ("เงิน", "silver"),
)
_SYNONYMS: dict[str, tuple[str, ...]] = {}
for _g in _SYNONYM_GROUPS:
    for _w in _g:
        _SYNONYMS.setdefault(_w, _g)

# คำไทยตั้งต้นสำหรับตัดคำ — ที่เหลือดึงจากชื่อหมวด/สี/สไตล์ในฐานเอง (ดู load_vocab)
_BASE_WORDS: tuple[str, ...] = tuple(w for g in _SYNONYM_GROUPS for w in g if w[0] >= THAI_LO) + (
    "ที่นั่ง", "บานเลื่อน", "บานเปิด", "ปรับระดับ", "พับได้", "เข้ามุม", "ตัวแอล",
    "สองชั้น", "สามชั้น", "ขนาด", "ฟุต", "นิ้ว", "เมตร", "เด็ก", "สนาม", "นอกบ้าน",
    "อเนกประสงค์", "พักผ่อน", "ทานอาหาร", "รับแขก", "แต่งตัว", "เก็บของ", "วางของ",
    "สปริง", "ยางพารา", "หัวเตียง", "ปลายเตียง", "ชุดโต๊ะ", "ชุดเตียง",
)


def is_thai(ch: str) -> bool:
    return THAI_LO <= ch <= THAI_HI


def normalize(s: str | None) -> str:
    """ทำคำค้นให้เป็นรูปเดียว — ตัวพิมพ์เล็ก, เลขไทยเป็นอารบิก, เครื่องหมายกลายเป็นช่องว่าง

    เครื่องหมายถูกตัดรวมถึง % และ _ ซึ่งเป็น wildcard ของ LIKE ด้วย — ปล่อยไว้ลูกค้าพิมพ์ %
    มาทีเดียวก็กลายเป็น "ขอทุกอย่าง" โดยไม่ได้ตั้งใจ
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFC", s).translate(_THAI_DIGITS).lower()
    return _PUNCT.sub(" ", s).strip()


def looks_like_code(t: str) -> bool:
    """เป็นรหัสสินค้า/บาร์โค้ดไหม — ตัวเลขล้วนตั้งแต่ 4 หลัก (MATNR ที่ขึ้นเว็บคือ 8 หลัก)"""
    return bool(_CODE.match(t))


def code_variants(t: str) -> list[str]:
    """รูปของรหัสตัวเดียวกันที่ต้องลองจับให้ครบ

    SAP เก็บ MATNR เป็น 18 หลักเติมศูนย์หน้า ส่วนฐานเรากับใบเสร็จใช้แบบตัดศูนย์ — เซลล์ก๊อป
    มาได้ทั้งสองแบบ จับทั้งตัวที่พิมพ์มา ตัวตัดศูนย์ และตัวเติมศูนย์ 18 หลัก
    """
    out = [t, t.lstrip("0") or t]
    if len(t) < 18:
        out.append((t.lstrip("0") or t).zfill(18))
    return list(dict.fromkeys(v for v in out if v))


class Vocab:
    """คลังคำสำหรับตัดคำไทย เดาคำผิด และตีความคำค้น — สร้างจากข้อมูลจริงในฐาน ไม่ใช่พจนานุกรมทั่วไป"""

    __slots__ = ("by_first", "latin", "colors", "categories")

    def __init__(self, thai: set[str], latin: set[str], colors: set[str], categories: dict[str, tuple[str, str]]):
        # แยกถังตามอักษรตัวแรกและเรียงยาว→สั้น ตัดคำจะได้ไม่ต้องไล่ทั้งคลังทุกตำแหน่ง
        buckets: dict[str, list[str]] = {}
        for w in thai:
            if len(w) >= 2:
                buckets.setdefault(w[0], []).append(w)
        self.by_first = {k: tuple(sorted(v, key=len, reverse=True)) for k, v in buckets.items()}
        self.latin = tuple(sorted(latin))
        self.colors = tuple(sorted(colors, key=len, reverse=True))  # ชื่อสีแบบตัดคำว่า "สี" ออกแล้ว
        self.categories = categories  # ชื่อหมวด (normalize แล้ว) → (id, ชื่อที่โชว์)


_CACHE: dict[str, tuple[float, Vocab]] = {}
_TTL = 600.0


def clear_cache() -> None:
    """เรียกหลังนำเข้าสินค้าใหม่ หรือในเทสต์ที่สลับฐาน"""
    _CACHE.clear()


def load_vocab(db: Session) -> Vocab:
    """ชื่อหมวด/สี/สไตล์/ชื่อรุ่น = คลังคำที่ตรงกับของที่ขายจริง แคชไว้ 10 นาที

    ใช้ข้อมูลในฐานแทนพจนานุกรมภาษาไทย เพราะคำที่ลูกค้าเฟอร์นิเจอร์พิมพ์มามีไม่กี่ร้อยคำ
    และล้วนโผล่อยู่ในชื่อหมวดกับชื่อรุ่นอยู่แล้ว — แม่นกว่าและไม่ต้องลงไลบรารีตัดคำ
    """
    from sqlalchemy import func

    from app.models.catalog import Brand, Category, Material  # วนกันเองถ้าดึงไว้บนสุด

    hit = _CACHE.get("vocab")
    if hit and monotonic() - hit[0] < _TTL:
        return hit[1]
    thai: set[str] = set(_BASE_WORDS)
    latin: set[str] = set()
    colors: set[str] = set()
    cats: dict[str, tuple[str, str, int]] = {}

    def feed(value: str | None) -> None:
        for run in _RUNS.findall(normalize(value)):
            if len(run) >= 2 and not run.isdigit():
                (thai if is_thai(run[0]) else latin).add(run)

    # ชื่อหมวด + จำนวนของ "ทั้งกิ่ง" — ชื่อเดียวกันมีหลาย id (คนละกิ่ง) และของมักเกาะอยู่ที่ใบ
    # หมวดแม่เลยนับตรงๆ ได้ 0 ทั้งที่มีของเต็มกิ่ง ต้องม้วนยอดขึ้นหาแม่ก่อนถึงเลือกกิ่งที่ถูกได้
    # นับของแยกจากการดึงหมวดแล้วมาต่อกันใน python — ให้ฐานทำ outer join + group by ทั้งสองตาราง
    # ช้ากว่านี้เป็นสิบเท่า (วัดบน SQLite: 3.3 วิ → 30 มิลลิ) และหมวดมีแค่หลักร้อยแถว
    direct = dict(db.execute(select(Material.category_id, func.count()).where(Material.is_public.is_(True)).group_by(Material.category_id)).all())
    tree = db.execute(select(Category.id, Category.parent_id, Category.name_th)).all()
    parent_of = {cid: pid for cid, pid, _ in tree}
    total: dict[str, int] = {cid: 0 for cid, _, _ in tree}
    for cid, _, _ in tree:
        n = int(direct.get(cid) or 0)
        node: str | None = cid
        for _ in range(5):  # กันวนไม่รู้จบถ้าข้อมูลหมวดพันกันเอง
            if node is None or node not in total:
                break
            total[node] += n
            node = parent_of.get(node)
    for cid, _, name in tree:
        key = normalize(name)
        # เก็บชื่อหมวดทั้งวลีด้วย เช่น "เก้าอี้พักผ่อนหนังแท้" — ตัดคำจะได้เลือกทั้งก้อนก่อนหั่นย่อย
        thai.add(key)
        feed(name)
        if total[cid] and (key not in cats or total[cid] > cats[key][2]):
            cats[key] = (cid, name, total[cid])
    for col in db.scalars(select(Material.color).distinct().limit(400)):
        base = strip_color_prefix(normalize(col))
        if 2 <= len(base) <= 24:
            colors.add(base)
        feed(col)
    for st in db.scalars(select(Material.style).distinct().limit(100)):
        feed(st)
    for name in db.scalars(select(Brand.name)):
        feed(name)
    for var in db.scalars(select(Material.variant).distinct().limit(4000)):
        feed(var)
    # ชื่อรุ่นภาษาอังกฤษส่วนใหญ่ฝังอยู่ในชื่อไทย ("โต๊ะกลาง รุ่น Adorn สีขาว") ไม่ได้อยู่ช่อง variant
    # เสมอไป — กวาดคำอังกฤษจากชื่อมาไว้เดาคำผิดด้วย (สแกนคอลัมน์เดียว ~50 มิลลิ ต่อ 10 นาที)
    for th, en in db.execute(select(Material.name_th, Material.name_en).where(Material.is_public.is_(True))):
        for run in _RUNS.findall(normalize(th) + " " + normalize(en)):
            if len(run) >= 4 and not run.isdigit() and not is_thai(run[0]):
                latin.add(run)
    v = Vocab(thai, latin, colors, {k: (cid, name) for k, (cid, name, _) in cats.items()})
    _CACHE["vocab"] = (monotonic(), v)
    return v


def segment(word: str, vocab: Vocab) -> list[str]:
    """ตัดคำไทยที่เขียนติดกันแบบ longest-match — "โซฟาหนัง" → ["โซฟา", "หนัง"]

    เลือกคำยาวสุดที่ตรงคลังคำก่อนเสมอ ชื่อหมวดอย่าง "โซฟาหนังแท้" จึงไม่ถูกหั่นเป็นสามท่อน
    ส่วนที่ไม่มีในคลังเก็บรวมเป็นก้อนเดียวไว้ ไม่ทิ้ง เพราะมักเป็นชื่อรุ่นที่ทับศัพท์มา
    """
    if len(word) < 4:
        return [word]
    out: list[str] = []
    buf = ""
    i = 0
    while i < len(word):
        hit = next((w for w in vocab.by_first.get(word[i], ()) if word.startswith(w, i)), None)
        if hit:
            if len(buf) >= 2:
                out.append(buf)
            buf = ""
            out.append(hit)
            i += len(hit)
        else:
            buf += word[i]
            i += 1
    if len(buf) >= 2:
        out.append(buf)
    return out or [word]


def spell_fix(word: str, vocab: Vocab) -> str | None:
    """เดาชื่อรุ่น/แบรนด์ที่พิมพ์ผิด — "adron" → "adorn" ใช้ตอนค้นแล้วไม่เจออะไรเลยเท่านั้น

    difflib อย่างเดียวเลือกผิดบ่อย ("adron" ได้ "madon" มาก่อน "adorn") เลยเอาผู้สมัคร
    มาหลายตัวแล้วจัดอันดับเอง: สลับตัวอักษรกันเฉยๆ (ตัวอักษรชุดเดียวกัน) น่าจะใช่ที่สุด
    รองมาคือขึ้นต้นตัวเดียวกัน — คนพิมพ์ผิดกลางคำมากกว่าพิมพ์ตัวแรกผิด
    """
    if len(word) < 4 or not word.isascii() or word in vocab.latin:
        return None
    cands = [c for c in get_close_matches(word, vocab.latin, n=8, cutoff=0.8) if c != word]
    if not cands:
        return None
    key = sorted(word)
    return max(cands, key=lambda c: (sorted(c) == key, c[0] == word[0], len(c) == len(word), -cands.index(c)))


@dataclass
class QueryToken:
    """หนึ่งคำที่ลูกค้าพิมพ์ พร้อมทางที่ยอมให้นับว่า "ตรง" ได้"""

    raw: str
    variants: list[str] = field(default_factory=list)   # ตรงตัวใดตัวหนึ่งก็เข้า (คำพ้อง)
    segments: list[str] = field(default_factory=list)   # หรือเข้าครบทุกคำย่อยหลังตัดคำ


@dataclass
class AnalyzedQuery:
    raw: str
    norm: str
    tokens: list[QueryToken] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)   # รูปต่างๆ ของรหัสที่พิมพ์มา
    corrected: str | None = None                     # คำหลังแก้ตัวสะกด ถ้ามีการแก้

    @property
    def empty(self) -> bool:
        return not self.tokens and not self.codes


def analyze(db: Session, q: str, spell: bool = False) -> AnalyzedQuery:
    """แปลงคำค้นดิบเป็นชุดเงื่อนไขที่ชั้น SQL เอาไปประกอบเป็น where/score ได้เลย

    spell=True เปิดการเดาคำผิด — ตั้งใจให้เรียกเฉพาะรอบ fallback ตอนค้นปกติแล้วไม่เจอ
    เพราะการเดาคำมีต้นทุน และถ้าเจอของอยู่แล้วก็ไม่ควรไปเปลี่ยนคำที่ลูกค้าพิมพ์
    """
    norm = normalize(q)
    a = AnalyzedQuery(raw=q or "", norm=norm)
    if not norm:
        return a
    vocab = load_vocab(db)
    changed = False
    words: list[str] = []
    for run in _RUNS.findall(norm)[:MAX_TOKENS]:
        if looks_like_code(run):
            a.codes += code_variants(run)
            words.append(run)
            continue
        word = run
        if spell:
            better = spell_fix(word, vocab)
            if better:
                word, changed = better, True
        words.append(word)
        segs = [word] if word.isascii() else segment(word, vocab)
        a.tokens.append(QueryToken(raw=word, variants=list(dict.fromkeys([word, *_SYNONYMS.get(word, ())])), segments=segs))
    if changed:
        a.corrected = " ".join(words)
    return a


# ---------------------------------------------------------------------------
# ชั้นตีความคำค้น (search แบบที่สอง)
#
# ชั้นบนเป็นการ "จับคำให้ตรง" — พิมพ์ "โต๊ะ" ต้องได้โต๊ะทุกตัว ชั้นนี้ทำคนละอย่าง คือ
# อ่านประโยคอย่าง "ตู้เสื้อผ้าสีแดง สูง 180 ไม่เกิน 5 พัน" แล้วแปลงเป็น "ตัวกรอง" —
# หมวด=ตู้เสื้อผ้า สี=แดง สเปกมี 180 ราคา<=5000 — แทนที่จะเอาทั้งประโยคไปไล่จับตัวอักษร
# (วงการเรียกว่า query understanding / attribute extraction ทำก่อนถึงจะไปหา vector)
# ---------------------------------------------------------------------------

_COLOR_PREFIX = ("สี", "colour ", "color ")
_UNIT_WORDS = {"ซม", "ซม.", "cm", "เซนติเมตร", "นิ้ว", "inch", "ฟุต", "ft", "เมตร", "ที่นั่ง", "seater",
               "ประตู", "บาน", "ชั้น", "ลิ้นชัก", "ที่นั่งl", "q", "kg"}
_DIM_WORDS = {"สูง", "กว้าง", "ยาว", "ลึก", "ขนาด", "หนา", "เส้นผ่านศูนย์กลาง"}
_MAX_WORDS = {"ไม่เกิน", "ต่ำกว่า", "ถูกกว่า", "งบ", "under", "ราคาไม่เกิน", "ในงบ"}
_MIN_WORDS = {"มากกว่า", "เกิน", "ขึ้นไป", "over", "เริ่มต้น"}
_MULTIPLIER = {"พัน": 1000, "หมื่น": 10000, "แสน": 100000, "ล้าน": 1000000, "k": 1000}
_NOISE = {"แบบ", "รุ่น", "สี", "ราคา", "บาท", "ที่", "ของ", "และ", "หรือ", "อยาก", "ได้", "หา", "มี", "เป็น"}
_PRICE_FLOOR = 100  # ต่ำกว่านี้ถือว่าเป็นเลขสเปก (เช่น 180 ซม.) ไม่ใช่งบประมาณ


def strip_color_prefix(s: str) -> str:
    for p in _COLOR_PREFIX:
        if s.startswith(p) and len(s) > len(p) + 1:
            return s[len(p):].strip()
    return s


@dataclass
class Interpretation:
    """สิ่งที่ระบบ "เข้าใจ" จากประโยคที่ลูกค้าพิมพ์ — เอาไปทำเป็นตัวกรองจริงและชิปบอกผู้ใช้"""

    category_id: str | None = None
    category_name: str | None = None
    color: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    specs: list[str] = field(default_factory=list)   # เลขสเปกที่ต้องปรากฏในชื่อ/สเปก เช่น "180"
    terms: list[str] = field(default_factory=list)   # คำที่เหลือ ค้นเป็นข้อความตามปกติ
    labels: list[str] = field(default_factory=list)  # ข้อความสรุปให้ผู้ใช้เห็นว่าตีความว่าอะไร
    dropped: list[str] = field(default_factory=list)  # เงื่อนไขที่ต้องยอมตัดทิ้งถึงจะเจอของ

    @property
    def useful(self) -> bool:
        """คุ้มที่จะสลับมาโหมดตีความไหม

        ต้องมี สี / ราคา / ขนาด อย่างน้อยหนึ่งอย่าง — ได้มาแค่ "หมวด" ไม่นับ เพราะพิมพ์
        "โต๊ะ" คำเดียวแล้วไปกรองด้วยหมวดชื่อ "โต๊ะ" จะเหลือของแค่หยิบมือ ทั้งที่โต๊ะจริงๆ
        กระจายอยู่ในหมวดลูกอีกสิบกว่าหมวด — เคสแบบนี้โหมดจับคำให้ผลครบกว่าเสมอ
        """
        return bool(self.color or self.max_price or self.min_price or self.specs)


def _units(norm: str, vocab: Vocab) -> list[str]:
    """แตกประโยคเป็นหน่วยย่อยที่ตีความต่อได้ — ไทยผ่านการตัดคำ ส่วนเลข/อังกฤษแยกอยู่แล้ว"""
    out: list[str] = []
    for run in _RUNS.findall(norm):
        out += segment(run, vocab) if is_thai(run[0]) else [run]
    return out


def interpret(db: Session, q: str) -> Interpretation:
    """อ่านประโยคค้นหาแล้วดึง หมวด / สี / ราคา / เลขสเปก ออกมาเป็นตัวกรอง"""
    ip = Interpretation()
    norm = normalize(q)
    if not norm:
        return ip
    vocab = load_vocab(db)
    units = _units(norm, vocab)
    i = 0
    while i < len(units):
        u = units[i]
        nxt = units[i + 1] if i + 1 < len(units) else ""
        prev = units[i - 1] if i else ""

        if u.isdigit():
            if looks_like_code(u) and prev not in _MAX_WORDS and prev not in _MIN_WORDS:
                ip.terms.append(u)  # รหัสสินค้า ไม่ใช่ตัวเลขสเปกและไม่ใช่งบ — ปล่อยให้ชั้นจับคำจัดการ
                i += 1
                continue
            n = float(u)
            mult = _MULTIPLIER.get(nxt)
            if mult:
                n *= mult
            # เลขจะเป็น "งบ" ต่อเมื่อมีคำบอกราคากำกับจริงๆ เท่านั้น — เลขลอยๆ อย่าง "180" หรือ
            # "20000" เดาเองไม่ได้ว่าเป็นราคาหรือขนาด เดาผิดแล้วผลลัพธ์เพี้ยนกว่าเดิม
            cue = prev in _MAX_WORDS or prev in _MIN_WORDS or nxt == "บาท" or (mult and n >= _PRICE_FLOOR)
            if cue:
                if prev in _MIN_WORDS:
                    ip.min_price = n
                    ip.labels.append(f"ราคาตั้งแต่ {n:,.0f} บาท")
                else:
                    ip.max_price = n
                    ip.labels.append(f"ราคาไม่เกิน {n:,.0f} บาท")
            else:
                ip.specs.append(u)
                if nxt in _UNIT_WORDS:
                    ip.terms.append(nxt)  # "6" เฉยๆ กว้างไป — บังคับให้มี "ฟุต" อยู่ด้วย
                ip.labels.append(f"{prev} {u} {nxt}".strip() if prev in _DIM_WORDS or nxt in _UNIT_WORDS else u)
            i += 2 if (mult or nxt in _UNIT_WORDS or nxt == "บาท") else 1
            continue

        hit = vocab.categories.get(u)
        if hit and not ip.category_id:
            ip.category_id, ip.category_name = hit
            ip.labels.append(f"หมวด {hit[1]}")
            i += 1
            continue

        base = strip_color_prefix(u)
        if not ip.color and base in vocab.colors and (u != base or prev == "สี" or len(base) > 2):
            ip.color = base
            ip.labels.append(f"สี{base}")
            i += 1
            continue

        if u not in _NOISE and u not in _UNIT_WORDS and u not in _DIM_WORDS and u not in _MAX_WORDS and u not in _MIN_WORDS:
            ip.terms.append(u)
        i += 1
    return ip
