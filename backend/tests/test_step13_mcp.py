"""MCP server — ให้ Claude ค้นสินค้า เช็คสต็อก และออกใบเสนอราคาผ่าน API ชุดเดียวกับหน้าเว็บ

เทสไม่ได้เปิด process จริง แต่ยิง JSON-RPC เข้า Server.handle ตรงๆ ส่วน Api ถูกสวมให้
วิ่งผ่าน TestClient แทน HTTP จริง — เส้นทางที่เทสคือ "เครื่องมือแต่ละตัวเรียก endpoint ถูกไหม"
"""
import json

import pytest

from app.db.session import SessionLocal
from app.mcp.api import Api
from app.mcp.server import Server
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


class FakeApi(Api):
    """Api ตัวเดิมทุกอย่าง ยกเว้นให้ call() วิ่งผ่าน TestClient แทน httpx จริง"""

    def __init__(self, client, headers):
        super().__init__()
        self.client = client
        self.headers = headers
        self._token = "test"
        self._me = {"role": "sales"}

    def call(self, method, path, *, json=None, params=None, retry=True):
        r = self.client.request(method, path, json=json, params=params, headers=self.headers)
        if r.status_code >= 400:
            from app.mcp.api import ApiError

            raise ApiError(f"{method} {path} -> {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else None


@pytest.fixture
def mcp(client):
    s = Server()
    s.api = FakeApi(client, auth_headers(client, "SA-104", "staff"))
    return s


def rpc(server, method, params=None, rid=1):
    return server.handle({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})


def payload(res):
    """ผลของ tools/call กลับมาเป็นข้อความ JSON — แกะกลับเป็น dict"""
    assert res["result"].get("isError") is not True, res["result"]["content"][0]["text"]
    return json.loads(res["result"]["content"][0]["text"])


def call(server, name, **args):
    return payload(rpc(server, "tools/call", {"name": name, "arguments": args}))


# ---------- โปรโตคอล ----------


def test_initialize_and_tool_list(mcp):
    init = rpc(mcp, "initialize")["result"]
    assert init["serverInfo"]["name"] == "sbdesign" and init["capabilities"]["tools"] is not None
    names = {t["name"] for t in rpc(mcp, "tools/list")["result"]["tools"]}
    assert {"search_products", "check_stock", "create_quotation"} <= names
    for t in rpc(mcp, "tools/list")["result"]["tools"]:
        assert t["description"] and t["inputSchema"]["type"] == "object"
        # required ต้องเป็นชื่อที่มีอยู่จริงใน properties ไม่งั้น client เตรียม argument ไม่ถูก
        assert set(t["inputSchema"]["required"]) <= set(t["inputSchema"]["properties"])


def test_notification_gets_no_reply(mcp):
    assert mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_unknown_method_is_jsonrpc_error(mcp):
    assert rpc(mcp, "tools/nope")["error"]["code"] == -32601


def test_unknown_tool_and_missing_arg_are_soft_errors(mcp):
    """ผิดที่ argument ต้องตอบเป็นข้อความให้แก้เอง ไม่ใช่ error ที่ทำให้ client ตัดสาย"""
    assert rpc(mcp, "tools/call", {"name": "ไม่มีอยู่จริง"})["result"]["isError"] is True
    assert rpc(mcp, "tools/call", {"name": "get_product", "arguments": {}})["result"]["isError"] is True


def test_read_only_mode_hides_write_tools(mcp, monkeypatch):
    monkeypatch.setenv("SB_MCP_ALLOW_WRITE", "0")
    names = {t["name"] for t in rpc(mcp, "tools/list")["result"]["tools"]}
    assert "search_products" in names and "create_quotation" not in names
    assert rpc(mcp, "tools/call", {"name": "open_cart", "arguments": {}})["result"]["isError"] is True


# ---------- เครื่องมือ ----------


def test_search_and_get_product(mcp):
    res = call(mcp, "search_products", q="", limit=5)
    assert res["shown"] and all("matnr" in i and "name" in i for i in res["items"])
    one = call(mcp, "get_product", matnr=res["items"][0]["matnr"])
    assert one["matnr"] == res["items"][0]["matnr"]


def test_check_stock_sends_every_line_in_one_call(mcp):
    """หัวใจของชุดนี้: ของชิ้นเดียวกันสองบรรทัดต้องถูกหักกัน ไม่ใช่เห็นของเต็มทั้งคู่"""
    res = call(mcp, "check_stock", items=[{"matnr": "10025230", "qty": 3}, {"matnr": "10025230", "qty": 3}])
    assert res["source"] == "mock" and len(res["items"]) == 2
    assert res["items"][0]["ready_qty"] == 3 and res["items"][1]["ready_qty"] == 1  # mock มี 4 ชิ้น
    assert res["all_ok"] is False


def test_check_stock_batch_endpoint_needs_no_cart(client):
    h = auth_headers(client, "SA-104", "staff")
    r = client.post("/sales/availability/batch", json={"items": [{"matnr": "10023841", "qty": 1}]}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cart_id"] is None and body["all_ok"] is True and body["items"][0]["matnr"] == "10023841"
    assert client.post("/sales/availability/batch", json={"items": []}, headers=h).status_code == 422


def test_batch_check_is_staff_only(client):
    hc = auth_headers(client, "081-222-3333")
    assert client.post("/sales/availability/batch", json={"items": [{"matnr": "10023841"}]}, headers=hc).status_code == 403


def test_cart_flow_to_quotation(mcp):
    cart = call(mcp, "open_cart", label="ทดสอบ MCP")
    cid = cart["cart_id"]
    call(mcp, "attach_customer", cart_id=cid, customer_key="081-222-3333")
    c = call(mcp, "add_item", cart_id=cid, matnr="10023841", qty=1, supply_mode="takeaway")
    assert c["items"][0]["matnr"] == "10023841"
    avail = call(mcp, "check_cart_stock", cart_id=cid)
    assert avail["all_ok"] is True
    d = call(mcp, "quote_delivery", cart_id=cid, postcode="10110", address="ทดสอบ")
    assert d["slots"], "ต้องมีคิวว่างให้เลือกอย่างน้อยหนึ่งช่อง"
    call(mcp, "pick_slot", cart_id=cid, slot_id=d["slots"][0]["slot_id"])
    q = call(mcp, "create_quotation", cart_id=cid, note="จาก MCP")
    assert q["quotation_no"].startswith("QT-") and q["lines"][0]["matnr"] == "10023841"
    assert call(mcp, "get_quotation", quotation_no=q["quotation_no"])["grand_total"] == q["grand_total"]


def test_quotation_without_customer_is_refused_with_a_readable_message(mcp):
    """ข้อความจาก backend ต้องถึงมือ Claude ตรงๆ จะได้รู้ว่าต้องผูกลูกค้าก่อน"""
    cart = call(mcp, "open_cart", label="ยังไม่ผูกลูกค้า")
    call(mcp, "add_item", cart_id=cart["cart_id"], matnr="10023841", qty=1, supply_mode="takeaway")
    res = rpc(mcp, "tools/call", {"name": "create_quotation", "arguments": {"cart_id": cart["cart_id"]}})
    assert res["result"]["isError"] is True
    assert "ลูกค้า" in res["result"]["content"][0]["text"]
