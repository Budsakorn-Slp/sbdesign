import pytest

from app.db.session import SessionLocal
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


def _open(client, h, label=None):
    r = client.post("/sales/carts", json={"label": label}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_sales_holds_three_carts_without_mixing(client):
    h = auth_headers(client, "SA-104", "staff")
    a, b, c = _open(client, h, "ลูกค้า A"), _open(client, h, "ลูกค้า B"), _open(client, h)
    client.post(f"/sales/carts/{a['id']}/items", json={"matnr": "10023841", "qty": 1}, headers=h)
    client.post(f"/sales/carts/{b['id']}/items", json={"matnr": "10044290", "qty": 2}, headers=h)
    ra = client.get(f"/sales/carts/{a['id']}", headers=h).json()
    rb = client.get(f"/sales/carts/{b['id']}", headers=h).json()
    rc = client.get(f"/sales/carts/{c['id']}", headers=h).json()
    assert [it["matnr"] for it in ra["items"]] == ["10023841"] and ra["items"][0]["added_by"] == "sales"
    assert [it["matnr"] for it in rb["items"]] == ["10044290"] and rb["count"] == 2
    assert rc["items"] == []
    mine = client.get("/sales/carts", headers=h).json()
    ids = {x["id"] for x in mine}
    assert {a["id"], b["id"], c["id"]} <= ids
    assert all(x["expires_at"] for x in mine)


def test_other_sales_gets_403(client):
    h1 = auth_headers(client, "SA-104", "staff")
    h2 = auth_headers(client, "SA-105", "staff")
    a = _open(client, h1)
    assert client.get(f"/sales/carts/{a['id']}", headers=h2).status_code == 403
    assert client.post(f"/sales/carts/{a['id']}/items", json={"matnr": "10023841", "qty": 1}, headers=h2).status_code == 403
    assert client.delete(f"/sales/carts/{a['id']}", headers=h2).status_code == 403
    # ลูกค้าเข้า endpoint เซลล์ไม่ได้
    assert client.get("/sales/carts", headers=auth_headers(client, "081-222-3333")).status_code == 403
    assert client.get("/customers/search", params={"q": "1100"}, headers=auth_headers(client, "081-222-3333")).status_code == 403


def test_attach_customer_merges_online_cart_and_customer_sees_it(client):
    hc = auth_headers(client, "094-916-4600")
    # ลูกค้าใส่ของจากบ้าน
    online = client.post("/cart/items", json={"matnr": "10052277", "qty": 1}, headers=hc).json()
    assert online["owner_sales"] is None
    online_count = online["count"]
    hs = auth_headers(client, "SA-104", "staff")
    cart = _open(client, hs)
    client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": "10071100", "qty": 2, "plant_code": "BKN", "supply_mode": "takeaway"}, headers=hs)
    found = client.get("/customers/search", params={"q": "094-916"}, headers=hs).json()
    assert found and found[0]["sap_customer_no"] == "1100440182" and found[0]["online_cart_count"] == online_count
    r = client.post(f"/sales/carts/{cart['id']}/attach-customer", json={"customer_key": "1100440182"}, headers=hs)
    assert r.status_code == 200, r.text
    merged = r.json()
    assert merged["customer"]["points"] == 1250 and merged["count"] == online_count + 2
    mats = {it["matnr"]: it for it in merged["items"]}
    assert mats["10052277"]["added_by"] == "customer" and mats["10052277"]["price_tier"] == "standard"
    # ของที่เซลล์ใส่เข้าตะกร้าลูกค้าเลย ไม่มีขั้น "รอลูกค้ากดรับ" (ป้ายบอกที่มาอยู่ที่ตัวรายการ)
    assert mats["10071100"]["added_by"] == "sales" and mats["10071100"]["pending_ack"] is False
    # ลูกค้าเปิดตะกร้าตัวเอง → เห็นใบเดียวกันที่เซลล์ถือ พร้อมป้ายเซลล์เพิ่ม
    mine = client.get("/cart", headers=hc).json()
    assert mine["id"] == merged["id"] and mine["owner_sales"]["staff_code"] == "SA-104" and mine["pending_count"] == 0
    # ตะกร้าออนไลน์เดิมถูกปิดเป็น merged
    assert client.post(f"/carts/{online['id']}/merge", json={"source_cart_id": online["id"]}, headers=hc).status_code == 403
    # ปุ่มล้างป้าย "รอยืนยัน" ยังเรียกได้ (เผื่อตะกร้าเก่าที่ค้างป้ายไว้) แต่ไม่เปลี่ยนอะไรแล้ว
    lamp = mats["10071100"]
    acked = client.post(f"/cart/items/{lamp['id']}/ack", headers=hc).json()
    assert next(it for it in acked["items"] if it["id"] == lamp["id"])["pending_ack"] is False
    # เซลล์คนอื่นจะผูกลูกค้าคนเดียวกันไม่ได้
    h2 = auth_headers(client, "SA-105", "staff")
    c2 = _open(client, h2)
    assert client.post(f"/sales/carts/{c2['id']}/attach-customer", json={"customer_key": "1100440182"}, headers=h2).status_code == 409
    # ปิดเซสชัน → ตะกร้ากลับเป็นของลูกค้า, เซลล์หมดสิทธิ์ทันที
    closed = client.delete(f"/sales/carts/{cart['id']}", headers=hs).json()
    assert closed["outcome"] == "returned_to_customer"
    assert client.get(f"/sales/carts/{cart['id']}", headers=hs).status_code == 403
    after = client.get("/cart", headers=hc).json()
    assert after["id"] == merged["id"] and after["owner_sales"] is None and after["count"] == merged["count"]


def test_detach_returns_customer_items(client):
    hc = auth_headers(client, "081-222-3333")
    before = client.get("/cart", headers=hc).json()
    client.post("/cart/items", json={"matnr": "10054010", "qty": 1}, headers=hc)
    hs = auth_headers(client, "SA-104", "staff")
    cart = _open(client, hs)
    r = client.post(f"/sales/carts/{cart['id']}/attach-customer", json={"customer_key": "weera@email.com"}, headers=hs)
    assert r.status_code == 200, r.text
    client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": "10061050", "qty": 4}, headers=hs)
    r = client.delete(f"/sales/carts/{cart['id']}/attach-customer", headers=hs).json()
    assert r["customer"] is None and [it["matnr"] for it in r["items"]] == ["10061050"]
    mine = client.get("/cart", headers=hc).json()
    assert "10054010" in [it["matnr"] for it in mine["items"]] and mine["owner_sales"] is None
    assert mine["count"] == before["count"] + 1


def test_unknown_customer_404_and_sap_only_customer_gets_created(client):
    hs = auth_headers(client, "SA-104", "staff")
    cart = _open(client, hs)
    assert client.post(f"/sales/carts/{cart['id']}/attach-customer", json={"customer_key": "no-such@x.com"}, headers=hs).status_code == 404
    r = client.post(f"/sales/carts/{cart['id']}/attach-customer", json={"customer_key": "1100440310"}, headers=hs)  # มีเฉพาะใน SAP mock
    assert r.status_code == 200 and r.json()["customer"]["name"].startswith("บริษัท ทรัพย์ทวี")
