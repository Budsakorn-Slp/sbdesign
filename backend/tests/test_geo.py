"""ที่อยู่ไทย /geo — ไล่จากรหัสไปรษณีย์และไล่ลงจังหวัด/อำเภอ/ตำบล

ใส่ตัวอย่างเท่าที่ครอบกฎจริง: กรุงเทพ (เขต 1) · เชียงใหม่ (เขต 2) · แม่ฮ่องสอน (ปิดทั้งจังหวัด)
และรหัส 10270 ที่คร่อมสองอำเภอ ซึ่งเป็นเหตุผลที่ /geo/postcode คืนลิสต์ไม่ใช่ตัวเดียว
"""

import pytest
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.models.geo import ThaiGeo

ROWS = [
    # (sub_id, zip, sub_th, dist_id, dist_th, prov_id, prov_th, area, blocked)
    (1, "10100", "วัดสามพระยา", 101, "พระนคร", 1, "กรุงเทพมหานคร", 1, False),
    (2, "10100", "บ้านพานถม", 101, "พระนคร", 1, "กรุงเทพมหานคร", 1, False),
    (3, "10110", "คลองเตย", 102, "คลองเตย", 1, "กรุงเทพมหานคร", 1, False),
    (4, "10270", "สำโรงเหนือ", 201, "เมืองสมุทรปราการ", 2, "สมุทรปราการ", 1, False),
    (5, "10270", "บางเมือง", 202, "บางพลี", 2, "สมุทรปราการ", 1, False),
    (6, "50000", "ศรีภูมิ", 301, "เมืองเชียงใหม่", 3, "เชียงใหม่", 2, False),
    (7, "58000", "จองคำ", 401, "เมืองแม่ฮ่องสอน", 4, "แม่ฮ่องสอน", 2, True),
]


@pytest.fixture(autouse=True)
def _geo():
    with SessionLocal() as db:
        db.execute(delete(ThaiGeo))
        db.bulk_save_objects([
            ThaiGeo(subdistrict_id=s, zipcode=z, subdistrict_th=sth, district_id=d, district_th=dth,
                    province_id=p, province_th=pth, area_id=a, is_blocked=b)
            for s, z, sth, d, dth, p, pth, a, b in ROWS
        ])
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(delete(ThaiGeo))
        db.commit()


def test_provinces_area_and_representative_postcode(client):
    by_name = {p["name_th"]: p for p in client.get("/geo/provinces").json()}
    assert by_name["กรุงเทพมหานคร"]["area_id"] == 1
    assert by_name["กรุงเทพมหานคร"]["postcode"] == "10100"  # รหัสน้อยสุดของจังหวัด
    assert by_name["เชียงใหม่"]["area_id"] == 2


def test_province_all_blocked_is_not_serviceable(client):
    by_name = {p["name_th"]: p for p in client.get("/geo/provinces").json()}
    assert by_name["แม่ฮ่องสอน"]["serviceable"] is False
    assert by_name["เชียงใหม่"]["serviceable"] is True


def test_districts_then_subdistricts(client):
    ds = client.get("/geo/districts", params={"province_id": 1}).json()
    assert {d["name_th"] for d in ds} == {"พระนคร", "คลองเตย"}
    subs = client.get("/geo/subdistricts", params={"district_id": 101}).json()
    assert [s["name_th"] for s in subs] == ["บ้านพานถม", "วัดสามพระยา"]  # เรียงตามชื่อไทย
    assert all(s["zipcode"] == "10100" for s in subs)


def test_unknown_province_and_district_are_404(client):
    assert client.get("/geo/districts", params={"province_id": 999}).status_code == 404
    assert client.get("/geo/subdistricts", params={"district_id": 999}).status_code == 404


def test_postcode_spanning_two_districts_returns_all(client):
    hits = client.get("/geo/postcode/10270").json()
    assert len({h["district_th"] for h in hits}) == 2  # ไม่ยุบให้เหลือตัวเดียว จะได้ไม่เดาผิดแบบเงียบๆ
    assert all(h["province_th"] == "สมุทรปราการ" and h["area_id"] == 1 for h in hits)


def test_search_by_partial_postcode(client):
    """พิมพ์ "101" ต้องเห็นทั้ง 10100 และ 10110 — ค้นจากหน้ารหัส ไม่ใช่ต้องครบ 5 หลัก"""
    hits = client.get("/geo/search", params={"q": "101"}).json()
    assert {h["zipcode"] for h in hits} == {"10100", "10110"}
    assert [h["zipcode"] for h in hits] == sorted(h["zipcode"] for h in hits)
    first = hits[0]
    assert first["subdistrict_th"] and first["district_th"] and first["province_th"]  # ครบทั้งบรรทัด เลือกทีเดียวจบ


def test_search_by_name_and_limit(client):
    assert [h["subdistrict_th"] for h in client.get("/geo/search", params={"q": "คลองเตย"}).json()] == ["คลองเตย"]
    assert {h["province_th"] for h in client.get("/geo/search", params={"q": "สมุทรปราการ"}).json()} == {"สมุทรปราการ"}
    assert len(client.get("/geo/search", params={"q": "10", "limit": 2}).json()) == 2
    assert client.get("/geo/search", params={"q": "ไม่มีที่นี่"}).json() == []
    assert client.get("/geo/search", params={"q": ""}).status_code == 422


def test_postcode_blocked_flag_and_errors(client):
    assert client.get("/geo/postcode/58000").json()[0]["is_blocked"] is True
    assert client.get("/geo/postcode/1234").status_code == 422
    assert client.get("/geo/postcode/abcde").status_code == 422
    assert client.get("/geo/postcode/99999").status_code == 404
