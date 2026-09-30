import pytest
from starlette.websockets import WebSocketDisconnect

from app.db.session import SessionLocal
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed, login


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


def test_sales_add_pushes_event_to_customer_socket(client):
    cust = login(client, "081-222-3333")
    hc = {"Authorization": "Bearer " + cust["access_token"]}
    hs = auth_headers(client, "SA-105", "staff")
    cart = client.post("/sales/carts", json={}, headers=hs).json()
    client.post(f"/sales/carts/{cart['id']}/attach-customer", json={"customer_key": "weera@email.com"}, headers=hs)
    my_cart_id = client.get("/cart", headers=hc).json()["id"]
    assert my_cart_id == cart["id"]
    with client.websocket_connect(f"/ws/cart/{my_cart_id}?token={cust['access_token']}") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["role"] == "customer"
        # เซลล์เพิ่มของ → ลูกค้าได้ event ทันที
        client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": "10044290", "qty": 1}, headers=hs)
        evt = ws.receive_json()
        assert evt["type"] == "item_added" and evt["matnr"] == "10044290" and evt["added_by"] == "sales" and evt["by_name"]
        # ลูกค้ากด "เก็บไว้" → เซลล์ (ห้องเดียวกัน) ก็ได้ event
        item_id = evt["item_id"]
        client.post(f"/cart/items/{item_id}/ack", headers=hc)
        evt2 = ws.receive_json()
        assert evt2["type"] == "item_acked" and evt2["item_id"] == item_id
        # ลบออก
        client.delete(f"/cart/items/{item_id}", headers=hc)
        assert ws.receive_json()["type"] == "item_removed"
        ws.send_text("ping")
        assert ws.receive_text() == "pong"
    client.delete(f"/sales/carts/{cart['id']}", headers=hs)


def test_socket_rejects_unauthorized(client):
    hs = auth_headers(client, "SA-105", "staff")
    cart = client.post("/sales/carts", json={}, headers=hs).json()
    other = login(client, "094-916-4600")
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/cart/{cart['id']}?token={other['access_token']}") as ws:
            ws.receive_json()
    assert exc.value.code == 1008
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/cart/{cart['id']}") as ws:  # ไม่มี token/anon
            ws.receive_json()
    client.delete(f"/sales/carts/{cart['id']}", headers=hs)


def test_guest_socket_with_anon_token(client):
    client.cookies.clear()
    r = client.get("/cart")
    anon = client.cookies.get("sb_anon")
    cart_id = r.json()["id"]
    with client.websocket_connect(f"/ws/cart/{cart_id}?anon={anon}") as ws:
        assert ws.receive_json()["role"] == "guest"
        client.post("/cart/items", json={"matnr": "10061050", "qty": 2})
        assert ws.receive_json()["type"] == "item_added"
