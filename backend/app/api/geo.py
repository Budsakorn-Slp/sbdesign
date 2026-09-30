"""ที่อยู่ไทย: เลือกจังหวัดคร่าวๆ บน nav แล้วค่อยกรอกเต็มตอน checkout

ลูกค้าอยากรู้ค่าส่งตั้งแต่ยังไม่ได้กรอกที่อยู่ ค่าส่งของเราขึ้นกับเขต (กทม.+ปริมณฑล / ต่างจังหวัด)
ซึ่งรู้ได้ตั้งแต่รู้จังหวัด — nav เลยเก็บแค่จังหวัด + รหัสไปรษณีย์ตัวแทน ส่วนตำบล/อำเภอ
ค่อยเลือกตอนกรอกที่อยู่จริง

    GET /geo/provinces               จังหวัดทั้งหมด + เขตค่าส่ง
    GET /geo/districts?province_id=  อำเภอในจังหวัด
    GET /geo/subdistricts?district_id=  ตำบล + รหัสไปรษณีย์
    GET /geo/postcode/{zipcode}      กรอกรหัสแล้วไล่ย้อนกลับ (รหัสเดียวมีได้หลายตำบล)
    GET /geo/search?q=               พิมพ์ไปหาไป — รหัสบางส่วนหรือชื่อตำบล/อำเภอ/จังหวัด
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.geo import ThaiGeo

router = APIRouter(prefix="/geo", tags=["geo"])


class ProvinceOut(BaseModel):
    province_id: int
    name_th: str
    name_en: str | None = None
    area_id: int | None = None
    postcode: str  # รหัสตัวแทนของจังหวัด ใช้ขอค่าส่งคร่าวๆ ก่อนรู้ที่อยู่เต็ม
    serviceable: bool  # ปิดครบทุกตำบล = ส่งไม่ได้ทั้งจังหวัด


class DistrictOut(BaseModel):
    district_id: int
    name_th: str
    name_en: str | None = None
    province_id: int
    serviceable: bool


class SubdistrictOut(BaseModel):
    subdistrict_id: int
    name_th: str
    name_en: str | None = None
    district_id: int
    zipcode: str
    area_id: int | None = None
    is_blocked: bool


class PostcodeHit(BaseModel):
    zipcode: str
    subdistrict_id: int
    subdistrict_th: str
    district_id: int
    district_th: str
    province_id: int
    province_th: str
    area_id: int | None = None
    is_blocked: bool


@router.get("/provinces", response_model=list[ProvinceOut])
def provinces(db: Session = Depends(get_db)):
    """เรียงตามชื่อไทย · postcode ตัวแทนเอารหัสน้อยสุดของจังหวัดที่ยังส่งได้"""
    rows = db.execute(
        select(ThaiGeo.province_id, ThaiGeo.province_th, ThaiGeo.province_en, ThaiGeo.area_id,
               func.min(ThaiGeo.zipcode), func.min(ThaiGeo.is_blocked))
        .group_by(ThaiGeo.province_id, ThaiGeo.province_th, ThaiGeo.province_en, ThaiGeo.area_id)
        .order_by(ThaiGeo.province_th)
    ).all()
    # จังหวัดหนึ่งอาจคาบสองเขต (ยังไม่มีในข้อมูลจริง แต่กันไว้) — ยุบเป็นแถวเดียว เอาเขตที่ตำบลส่วนใหญ่อยู่
    out: dict[int, ProvinceOut] = {}
    for pid, th, en, area, zipcode, blocked_min in rows:
        cur = out.get(pid)
        if cur is None:
            out[pid] = ProvinceOut(province_id=pid, name_th=th, name_en=en, area_id=area,
                                   postcode=zipcode, serviceable=not blocked_min)
        elif zipcode < cur.postcode:
            cur.postcode = zipcode
    return sorted(out.values(), key=lambda p: p.name_th)


def _bare(name: str) -> str:
    """ตัดคำนำหน้าออกเพื่อใช้เป็นคีย์เทียบ — ต้นทางเขียนไม่เหมือนกัน (อ.ขนอม / อำเภอขนอม)"""
    v = (name or "").strip()
    for p in ("อำเภอ", "เขต", "อ."):
        if v.startswith(p):
            return v[len(p):].strip()
    return v


def district_siblings(db: Session, district_id: int) -> list[int]:
    """id ทั้งหมดที่จริงๆ แล้วคืออำเภอเดียวกัน

    ต้นทางมีอำเภอซ้ำ 7 คู่ (เช่น 638 "อำเภอเกาะพะงัน" กับ 639 "อ.เกาะพะงัน") แต่ละ id
    ถือตำบลคนละชุด · เวลายุบให้เหลือรายการเดียวจึงต้องรวมตำบลของพี่น้องมาด้วย
    ไม่งั้นเลือกอำเภอแล้วตำบลหายไปครึ่งหนึ่งโดยไม่มีใครรู้
    """
    row = db.execute(select(ThaiGeo.province_id, ThaiGeo.district_th).where(ThaiGeo.district_id == district_id).limit(1)).first()
    if not row:
        return [district_id]
    pv, th = row
    ids = db.execute(select(ThaiGeo.district_id, ThaiGeo.district_th).where(ThaiGeo.province_id == pv).group_by(ThaiGeo.district_id)).all()
    key = _bare(th)
    return [d for d, name in ids if _bare(name) == key] or [district_id]


@router.get("/districts", response_model=list[DistrictOut])
def districts(province_id: int = Query(...), db: Session = Depends(get_db)):
    rows = db.execute(
        select(ThaiGeo.district_id, ThaiGeo.district_th, ThaiGeo.district_en, func.min(ThaiGeo.is_blocked))
        .where(ThaiGeo.province_id == province_id)
        .group_by(ThaiGeo.district_id, ThaiGeo.district_th, ThaiGeo.district_en)
        .order_by(ThaiGeo.district_th)
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="ไม่พบจังหวัดนี้")
    # ยุบอำเภอที่ซ้ำให้เหลือรายการเดียว — เลือกชื่อที่เขียนเต็ม ("อำเภอขนอม") เป็นตัวแทน
    # และเอา id น้อยสุดเป็นค่าที่ส่งกลับ ส่วนตำบลจะถูกรวมให้ตอนเรียก /subdistricts
    merged: dict[str, dict] = {}
    for d, th, en, b in rows:
        k = _bare(th)
        cur = merged.get(k)
        full = th.startswith(("อำเภอ", "เขต"))
        if cur is None:
            merged[k] = {"id": d, "th": th, "en": en, "blocked": b, "full": full}
            continue
        cur["id"] = min(cur["id"], d)
        cur["blocked"] = min(cur["blocked"], b)
        if full and not cur["full"]:
            cur["th"], cur["en"], cur["full"] = th, en, True
    return [DistrictOut(district_id=v["id"], name_th=v["th"], name_en=v["en"], province_id=province_id, serviceable=not v["blocked"])
            for v in sorted(merged.values(), key=lambda v: v["th"])]


@router.get("/subdistricts", response_model=list[SubdistrictOut])
def subdistricts(district_id: int = Query(...), db: Session = Depends(get_db)):
    # รวมตำบลของอำเภอที่ซ้ำกันมาด้วย (ดู district_siblings) ไม่งั้นตำบลหายไปครึ่ง
    rows = db.scalars(
        select(ThaiGeo).where(ThaiGeo.district_id.in_(district_siblings(db, district_id))).order_by(ThaiGeo.subdistrict_th)
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="ไม่พบอำเภอนี้")
    return [SubdistrictOut(subdistrict_id=r.subdistrict_id, name_th=r.subdistrict_th, name_en=r.subdistrict_en,
                           district_id=r.district_id, zipcode=r.zipcode, area_id=r.area_id, is_blocked=r.is_blocked)
            for r in rows]


def _hit(r: ThaiGeo) -> PostcodeHit:
    return PostcodeHit(zipcode=r.zipcode, subdistrict_id=r.subdistrict_id, subdistrict_th=r.subdistrict_th,
                       district_id=r.district_id, district_th=r.district_th, province_id=r.province_id,
                       province_th=r.province_th, area_id=r.area_id, is_blocked=r.is_blocked)


@router.get("/search", response_model=list[PostcodeHit])
def search(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=50), db: Session = Depends(get_db)):
    """พิมพ์ไปหาไป — คืนบรรทัดเต็ม "ตำบล » อำเภอ » จังหวัด » รหัส" ให้เลือกทีเดียวจบ

    ลูกค้าจำได้ไม่เหมือนกัน บางคนจำรหัส บางคนจำชื่อตำบล เลยรับทั้งสองแบบ:
    ตัวเลขล้วน = ค้นจากหน้ารหัส (พิมพ์ "10" ก็เห็น 10100 ขึ้นมาแล้ว)
    ตัวหนังสือ = ค้นชื่อตำบล/อำเภอ/จังหวัด แบบมีคำนี้อยู่ข้างใน
    """
    term = (q or "").strip()
    if not term:
        return []
    stmt = select(ThaiGeo)
    if term.isdigit():
        stmt = stmt.where(ThaiGeo.zipcode.like(f"{term}%"))
    else:
        like = f"%{term}%"
        stmt = stmt.where(ThaiGeo.subdistrict_th.like(like) | ThaiGeo.district_th.like(like) | ThaiGeo.province_th.like(like))
    rows = db.scalars(
        stmt.order_by(ThaiGeo.zipcode, ThaiGeo.province_th, ThaiGeo.district_th, ThaiGeo.subdistrict_th).limit(limit)
    ).all()
    return [_hit(r) for r in rows]


@router.get("/postcode/{zipcode}", response_model=list[PostcodeHit])
def by_postcode(zipcode: str, db: Session = Depends(get_db)):
    """กรอกรหัส 5 หลักแล้วเติมจังหวัด/อำเภอให้เอง — เหลือให้เลือกแค่ตำบล

    คืนเป็นลิสต์เสมอ ไม่ยุบให้เหลือตัวเดียว: 922 รหัสกระจายอยู่ 7,391 ตำบล
    รหัสเดียวคร่อมหลายอำเภอก็มี ถ้าเดาให้จะได้ที่อยู่ผิดแบบเงียบๆ
    """
    pc = (zipcode or "").strip()
    if len(pc) != 5 or not pc.isdigit():
        raise HTTPException(status_code=422, detail="รหัสไปรษณีย์ต้องเป็นตัวเลข 5 หลัก")
    rows = db.scalars(
        select(ThaiGeo).where(ThaiGeo.zipcode == pc).order_by(ThaiGeo.province_th, ThaiGeo.district_th, ThaiGeo.subdistrict_th)
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="ไม่พบรหัสไปรษณีย์นี้")
    return [_hit(r) for r in rows]
