"""รายการเครื่องมือที่เปิดให้ Claude เรียก — ค้นสินค้า เช็คสต็อก และออกใบเสนอราคา

หลักที่ยึดไว้ตอนออกแบบชุดนี้:
- เช็คสต็อกต้องยิงทั้งชุดครั้งเดียวเสมอ ไม่มีเครื่องมือ "เช็คทีละตัวแล้ววนเอง"
  เพราะ SAP จำลองใบสั่งขายทั้งใบ ยิงแยกทีละบรรทัดทุกบรรทัดจะเห็นของชิ้นเดียวกันซ้ำ = ขายเกิน
- ตัวเลขเงินทุกตัวมาจาก backend ไม่ให้ Claude คำนวณเอง (ส่วนลด/ค่าส่ง/VAT อยู่ที่ compute_totals จุดเดียว)
- เครื่องมือที่เปลี่ยนข้อมูลจริงมีแค่ตะกร้ากับใบเสนอราคา ไม่มีเครื่องมือลบลูกค้า/แก้ราคา/แก้สต็อก
"""
from typing import Any, Callable

from app.mcp.api import Api

Handler = Callable[[Api, dict], Any]
TOOLS: list[dict] = []


def tool(name: str, description: str, properties: dict, required: list[str] | None = None):
    def deco(fn: Handler) -> Handler:
        TOOLS.append({
            "name": name,
            "description": description,
            "inputSchema": {"type": "object", "properties": properties, "required": required or []},
            "handler": fn,
        })
        return fn

    return deco


STR = {"type": "string"}
INT = {"type": "integer"}
NUM = {"type": "number"}
BOOL = {"type": "boolean"}


# ---------- สินค้า ----------
def _card(m: dict) -> dict:
    out = {
        "matnr": m["matnr"], "name": m.get("name_th"), "variant": m.get("variant"),
        "price": m.get("price"), "price_tier": m.get("price_tier"), "standard_price": m.get("standard_price"),
        "category": m.get("category_name"), "brand": m.get("brand_name"), "room": m.get("room"),
        "requires_install": m.get("requires_install"), "is_takeaway_ok": m.get("is_takeaway_ok"),
    }
    if m.get("discount_percent"):
        out["discount_percent"] = m["discount_percent"]
    return {k: v for k, v in out.items() if v is not None}


@tool(
    "search_products",
    "ค้นหาสินค้าในแค็ตตาล็อก SB Design Square (คืน MATNR ที่ใช้ต่อกับเครื่องมืออื่น) "
    "ตัวเลขสต็อกไม่ได้มาจากที่นี่ — ต้องเรียก check_stock อีกที",
    {
        "q": {**STR, "description": "คำค้น เช่น ชื่อรุ่น/ประเภท/MATNR"},
        "category": {**STR, "description": "รหัสหมวด (ได้จาก list_categories)"},
        "room": {**STR, "description": "ห้อง เช่น bedroom, living"},
        "brand": {"type": "array", "items": STR, "description": "กรองหลายแบรนด์ได้"},
        "min_price": NUM, "max_price": NUM,
        "discount_only": BOOL,
        "sort": {**STR, "description": "relevance | price_asc | price_desc | new | discount | bestseller"},
        "limit": {**INT, "description": "ค่าเริ่มต้น 12 สูงสุด 50"},
        "offset": INT,
    },
)
def search_products(api: Api, a: dict) -> Any:
    limit = min(int(a.get("limit") or 12), 50)
    res = api.get(
        "/materials/search", q=a.get("q"), category=a.get("category"), room=a.get("room"),
        brand=a.get("brand"), min_price=a.get("min_price"), max_price=a.get("max_price"),
        discount_only=a.get("discount_only"), sort=a.get("sort"), limit=limit, offset=a.get("offset") or 0,
    )
    return {"total": res["total"], "shown": len(res["items"]), "items": [_card(m) for m in res["items"]]}


@tool("get_product", "รายละเอียดสินค้าหนึ่งตัวจาก MATNR (สเปก ขนาด สีอื่นของรุ่นเดียวกัน)", {"matnr": STR}, ["matnr"])
def get_product(api: Api, a: dict) -> Any:
    m = api.get(f"/materials/{a['matnr']}")
    out = _card(m)
    out.update({k: m.get(k) for k in ("description", "color", "style", "spec", "volume_m3", "weight_kg", "image_url") if m.get(k)})
    if m.get("colors"):
        out["other_colors"] = [{"matnr": c["matnr"], "color": c.get("color"), "price": c.get("price")} for c in m["colors"]]
    return out


@tool("list_categories", "ต้นไม้หมวดสินค้าที่มีของขายจริง — เอา id ไปใส่ search_products(category=...)", {})
def list_categories(api: Api, a: dict) -> Any:
    return [
        {"id": c["id"], "name": c["name_th"], "children": [{"id": ch["id"], "name": ch["name_th"]} for ch in c.get("children", [])]}
        for c in api.get("/categories")
    ]


# ---------- เช็คสต็อก ----------
def _avail(res: dict) -> dict:
    return {
        "source": res["source"],  # sap = ของจริง · mock = ข้อมูลจำลอง ห้ามเอาไปยืนยันกับลูกค้า
        "req_date": res["req_date"],
        "customer_no": res["customer_no"],
        "all_ok": res["all_ok"],
        "message": res["message"],
        "items": [
            {k: v for k, v in {
                "matnr": i["matnr"], "name": i.get("sap_name") or i.get("name"), "qty": i["qty"],
                "status": i["status"], "label": i["label"],
                "ready_qty": i["ready_qty"], "ready_date": i.get("ready_date"),
                "later_qty": i["later_qty"], "later_date": i.get("later_date"),
                "short_qty": i["short_qty"], "sap_unit_price": i.get("sap_unit_price"),
            }.items() if v not in (None, 0) or k in ("qty", "status", "matnr", "ready_qty", "short_qty")}
            for i in res["items"]
        ],
    }


@tool(
    "check_stock",
    "เช็คสต็อกกับ SAP — ส่งรายการทั้งหมดที่ลูกค้าจะซื้อไปพร้อมกันในครั้งเดียว "
    "ห้ามเรียกทีละรายการแล้วรวมผลเอง เพราะ SAP จำลองทั้งบิล ถ้าแยกยิงทุกบรรทัดจะเห็นของชิ้นเดียวกันซ้ำ (ขายเกิน) "
    "status: full=ได้ครบ · split=ได้ครบแต่แบ่งส่ง · short=ไม่พอ · none=ไม่มีของ · unknown=SAP ไม่รู้จักรหัสนี้",
    {
        "items": {
            "type": "array",
            "items": {"type": "object", "properties": {"matnr": STR, "qty": INT}, "required": ["matnr"]},
            "description": "ทุกรายการในบิลเดียวกัน (สูงสุด 25 บรรทัด)",
        },
        "customer_no": {**STR, "description": "เลขลูกค้า SAP ถ้ามี — ไม่ใส่จะใช้ลูกค้า walk-in"},
    },
    ["items"],
)
def check_stock(api: Api, a: dict) -> Any:
    items = [{"matnr": str(i["matnr"]), "qty": int(i.get("qty") or 1)} for i in a["items"]]
    return _avail(api.post("/sales/availability/batch", {"items": items, "customer_no": a.get("customer_no")}))


@tool("check_cart_stock", "เช็คสต็อกของทุกอย่างในตะกร้าใบนั้นครั้งเดียว (ใช้ก่อนออกใบเสนอราคา)", {"cart_id": STR}, ["cart_id"])
def check_cart_stock(api: Api, a: dict) -> Any:
    return _avail(api.post(f"/sales/carts/{a['cart_id']}/availability"))


# ---------- ลูกค้า ----------
@tool("search_customers", "ค้นลูกค้าด้วยเลขสมาชิก / เบอร์โทร / อีเมล", {"q": {**STR, "description": "อย่างน้อย 2 ตัวอักษร"}}, ["q"])
def search_customers(api: Api, a: dict) -> Any:
    return api.get("/customers/search", q=a["q"])


# ---------- ตะกร้า ----------
def _cart(c: dict) -> dict:
    t = c.get("totals") or {}
    return {
        "cart_id": c["id"], "cart_no": c["no"], "label": c.get("label"), "status": c.get("status"),
        "customer": (c.get("customer") or {}).get("name"),
        "sap_customer_no": (c.get("customer") or {}).get("sap_customer_no"),
        "items": [
            {"item_id": i["id"], "matnr": i["matnr"], "name": i["name"], "qty": i["qty"],
             "unit_price": i["unit_price"], "line_total": i["line_total"], "supply_mode": i["supply_mode"]}
            for i in c.get("items", [])
        ],
        "subtotal": c.get("subtotal"),
        "totals": {k: t.get(k) for k in ("discount_total", "shipping_fee", "install_fee", "vat_included", "grand_total") if t.get(k) is not None},
        "delivery": {k: (c.get("delivery") or {}).get(k) for k in ("postcode", "zone_name", "slot_date", "slot_period") if (c.get("delivery") or {}).get(k)},
    }


@tool("list_carts", "ตะกร้าทั้งหมดที่บัญชีเซลล์ของ MCP ถืออยู่", {})
def list_carts(api: Api, a: dict) -> Any:
    return api.get("/sales/carts")


@tool("open_cart", "เปิดตะกร้าใบใหม่ (ใบเสนอราคาหนึ่งใบ = ตะกร้าหนึ่งใบ)", {"label": {**STR, "description": "ชื่อกำกับ เช่น ชื่อลูกค้า"}})
def open_cart(api: Api, a: dict) -> Any:
    return _cart(api.post("/sales/carts", {"label": a.get("label")}))


@tool("view_cart", "ดูตะกร้าใบหนึ่ง พร้อมยอดรวมที่ backend คิดให้", {"cart_id": STR}, ["cart_id"])
def view_cart(api: Api, a: dict) -> Any:
    return _cart(api.get(f"/sales/carts/{a['cart_id']}"))


@tool(
    "add_item",
    "ใส่สินค้าลงตะกร้า (ราคาถูก snapshot ไว้ตอนใส่)",
    {
        "cart_id": STR, "matnr": STR, "qty": INT,
        "supply_mode": {**STR, "description": "takeaway=ยกกลับ · ship=จัดส่ง · install=ส่ง+ติดตั้ง · pickup=รับที่สาขา (ไม่ใส่ = ระบบเลือกให้)"},
    },
    ["cart_id", "matnr"],
)
def add_item(api: Api, a: dict) -> Any:
    body = {"matnr": a["matnr"], "qty": int(a.get("qty") or 1)}
    if a.get("supply_mode"):
        body["supply_mode"] = a["supply_mode"]
    return _cart(api.post(f"/sales/carts/{a['cart_id']}/items", body))


@tool("remove_item", "เอาสินค้าออกจากตะกร้า (item_id ได้จาก view_cart)", {"cart_id": STR, "item_id": STR}, ["cart_id", "item_id"])
def remove_item(api: Api, a: dict) -> Any:
    return _cart(api.delete(f"/sales/carts/{a['cart_id']}/items/{a['item_id']}"))


@tool(
    "attach_customer",
    "ผูกลูกค้ากับตะกร้า — ต้องทำก่อนออกใบเสนอราคาเสมอ (ราคาจะเปลี่ยนเป็นเรตสมาชิกของลูกค้าคนนั้น)",
    {"cart_id": STR, "customer_key": {**STR, "description": "เลขสมาชิก / เบอร์โทร / อีเมล"}},
    ["cart_id", "customer_key"],
)
def attach_customer(api: Api, a: dict) -> Any:
    return _cart(api.post(f"/sales/carts/{a['cart_id']}/attach-customer", {"customer_key": a["customer_key"]}))


# ---------- ค่าส่ง + คิว ----------
@tool(
    "quote_delivery",
    "คำนวณค่าขนส่งตามรหัสไปรษณีย์ + คืนคิวจัดส่งที่ว่าง (ต้องทำถ้ามีรายการแบบ ship/install)",
    {"cart_id": STR, "postcode": {**STR, "description": "5 หลัก"}, "address": STR},
    ["cart_id", "postcode"],
)
def quote_delivery(api: Api, a: dict) -> Any:
    r = api.post("/delivery/quote", {"cart_id": a["cart_id"], "postcode": a["postcode"], "address": a.get("address")})
    return {
        "zone": r["zone_name"], "base_fee": r["base_fee"], "install_fee": r["install_fee"], "total_fee": r["total_fee"],
        "groups": [{"mode": g["mode"], "label": g["label"], "items": len(g["items"])} for g in r["groups"]],
        "slots": [{"slot_id": s["id"], "date": s["date"], "period": s["period"], "remaining": s["remaining"]} for s in r["slots"] if s["remaining"] > 0][:12],
        "held_slot_id": r.get("held_slot_id"),
        "warnings": r.get("ship_warnings") or [],
    }


@tool("pick_slot", "จองคิวจัดส่ง (กันไว้ 15 นาที) — slot_id ได้จาก quote_delivery", {"cart_id": STR, "slot_id": STR}, ["cart_id", "slot_id"])
def pick_slot(api: Api, a: dict) -> Any:
    return api.post(f"/delivery/slots/{a['slot_id']}/hold", {"cart_id": a["cart_id"]})


# ---------- ใบเสนอราคา ----------
def _quotation(q: dict) -> dict:
    return {
        "quotation_no": q["quotation_no"], "status": q["status"], "valid_until": q["valid_until"],
        "customer": (q.get("customer") or {}).get("name"), "sales": q.get("sales_name"),
        "lines": [{"matnr": l["matnr"], "name": l["name"], "qty": l["qty"], "unit_price": l["unit_price"], "line_total": l["line_total"], "supply_mode": l["supply_mode"]} for l in q["lines"]],
        "discounts": [{"title": d.get("title") or d.get("code"), "amount": d["amount"]} for d in q.get("discounts", [])],
        "subtotal": q["subtotal"], "discount_total": q["discount_total"],
        "shipping_fee": q["shipping_fee"], "install_fee": q["install_fee"],
        "vat": q["vat"], "grand_total": q["grand_total"], "deposit_amount": q["deposit_amount"],
        "document_url": q.get("pdf_url"),
        "stock_warnings": q.get("stock_warnings"),
    }


@tool(
    "create_quotation",
    "ออกใบเสนอราคาจากตะกร้า — เซฟใบร่าง (Preso) แล้วออกเอกสารให้ในขั้นตอนเดียว "
    "backend จะยิงเช็คสต็อกสดก่อนเสมอ ของไม่พอจะไม่ออกให้ (ตอบกลับเป็นข้อผิดพลาดพร้อมรายการที่ขาด) "
    "ถ้าลูกค้ายืนยันว่ารับได้ค่อยเรียกซ้ำด้วย force=true · ออกแล้วแก้ไม่ได้ ต้อง cancel แล้วออกใหม่",
    {"cart_id": STR, "note": {**STR, "description": "หมายเหตุในใบร่าง"}, "force": {**BOOL, "description": "ออกทั้งที่ของไม่พอ"}},
    ["cart_id"],
)
def create_quotation(api: Api, a: dict) -> Any:
    # ใบ PRE มีด่านบังคับ (เช็คสต็อก + เช็คโปรฯ ต้องทำกับของชุดปัจจุบัน) — เดินให้ครบตรงนี้เลย
    # ผู้ช่วยจะได้ไม่ต้องสั่งทีละขั้น และผลที่ได้ตรงกับที่เซลล์กดเองในหน้าตะกร้า
    api.post(f"/sales/carts/{a['cart_id']}/availability", {})
    api.post("/promotions/evaluate", {"cart_id": a["cart_id"]})
    preso = api.post("/presos", {"cart_id": a["cart_id"], "note": a.get("note"), "force": bool(a.get("force"))})
    q = api.post(f"/presos/{preso['preso_no']}/quotation", {"force": bool(a.get("force"))})
    return {"preso_no": preso["preso_no"], **_quotation(q)}


@tool("get_quotation", "ดูใบเสนอราคาที่ออกไปแล้ว", {"quotation_no": STR}, ["quotation_no"])
def get_quotation(api: Api, a: dict) -> Any:
    return _quotation(api.get(f"/quotations/{a['quotation_no']}"))


@tool("list_quotations", "ใบเสนอราคาทั้งหมดของบัญชีเซลล์นี้", {})
def list_quotations(api: Api, a: dict) -> Any:
    return [{"quotation_no": q["quotation_no"], "status": q["status"], "customer": (q.get("customer") or {}).get("name"), "grand_total": q["grand_total"], "issued_at": q["issued_at"]} for q in api.get("/quotations")]


@tool("cancel_quotation", "ยกเลิกใบเสนอราคา (ต้องบอกเหตุผล)", {"quotation_no": STR, "reason": STR}, ["quotation_no", "reason"])
def cancel_quotation(api: Api, a: dict) -> Any:
    return _quotation(api.post(f"/quotations/{a['quotation_no']}/cancel", {"reason": a["reason"]}))


def by_name() -> dict[str, dict]:
    return {t["name"]: t for t in TOOLS}


def specs() -> list[dict]:
    return [{k: v for k, v in t.items() if k != "handler"} for t in TOOLS]
