"""STEP 11 — matrix สิทธิ์ครบทุก endpoint

วิธีตรวจ: ยิงทุก endpoint ด้วยทั้ง 5 บทบาท
- บทบาทที่ "ไม่มีสิทธิ์" ต้องได้ 401/403 เสมอ
- บทบาทที่ "มีสิทธิ์" ต้องไม่ได้ 401/403 (404/422/400 ถือว่าผ่านด่านสิทธิ์แล้ว)

ทุก request จงใจชี้ไปที่ของที่ไม่มีจริง (NOPE) หรือส่ง body ที่ไม่ผ่าน validation
เพื่อให้ผ่านด่านสิทธิ์แต่ไม่แก้ข้อมูลจริง (test อื่นใช้ DB ก้อนเดียวกัน)
"""
import pytest

from app.main import app
from tests.helpers import auth_headers, ensure_seed

G, C, S, M, A = "guest", "customer", "sales", "manager", "admin"
ALL = (G, C, S, M, A)
AUTH = (C, S, M, A)
CUST = (C,)  # ลูกค้าเท่านั้น (เซลล์ห้ามรับเงินเอง)
STAFF = (S, M)  # เซลล์ + ผู้จัดการ (เครื่องมือขาย)
MGR = (M, A)
EMP = (S, M, A)  # ทุกบัญชีพนักงาน (get_current_employee) — สิทธิ์ละเอียดตรวจตาม permission ต่อ
ADMIN = (A,)

BAD = "NOPE"  # id ที่ไม่มีจริง → handler ตอบ 404 หลังผ่านด่านสิทธิ์

# (method, path, roles ที่มีสิทธิ์, body)
MATRIX: list[tuple[str, str, tuple[str, ...], dict | None]] = [
    # ---------- สาธารณะ ----------
    ("GET", "/healthz", ALL, None),
    # หน้าเว็บต้องอ่านได้ก่อนล็อกอิน (ใช้ตัดสินว่าจะขึ้นหน้า "เร็ว ๆ นี้" ไหม) — ไม่มีข้อมูลลับ
    ("GET", "/public-config", ALL, None),
    ("GET", "/home", ALL, None),
    ("GET", f"/pages/{BAD}", ALL, None),  # หน้าเนื้อหาคงที่ — เปิดให้ทุกคนอ่าน ไม่ต้องล็อกอิน
    ("GET", "/categories", ALL, None),
    ("GET", "/brands", ALL, None),
    ("GET", "/plants", ALL, None),
    ("GET", "/materials/search?q=โซฟา", ALL, None),
    ("GET", "/materials/suggest?q=โซฟา", ALL, None),
    ("GET", f"/materials/{BAD}", ALL, None),
    ("GET", f"/materials/{BAD}/stock", ALL, None),
    ("GET", "/best-sellers", ALL, None),
    # ที่อยู่ไทย — เปิดสาธารณะ ต้องเลือกจังหวัดได้ก่อนล็อกอิน ไม่มีข้อมูลส่วนบุคคล
    ("GET", "/geo/provinces", ALL, None),
    ("GET", "/geo/districts?province_id=0", ALL, None),
    ("GET", "/geo/subdistricts?district_id=0", ALL, None),
    ("GET", "/geo/search?q=10", ALL, None),
    ("GET", f"/geo/postcode/{BAD}", ALL, None),  # ไม่ใช่ตัวเลข 5 หลัก -> 422 แต่ผ่านด่านสิทธิ์แล้ว
    ("POST", "/auth/register", ALL, {}),
    ("POST", "/auth/login", ALL, {}),
    ("POST", "/auth/refresh", ALL, {}),
    ("POST", "/auth/logout", ALL, {}),
    ("POST", "/auth/otp/request", ALL, {}),
    ("POST", "/auth/otp/verify", ALL, {}),
    ("POST", "/auth/password/forgot", ALL, {}),
    ("POST", "/auth/password/reset", ALL, {}),
    # ---------- ตะกร้าของตัวเอง (guest ก็ใช้ได้) ----------
    ("GET", "/cart", ALL, None),
    ("POST", "/cart/items", ALL, {}),
    ("PATCH", f"/cart/items/{BAD}", ALL, {}),
    ("DELETE", f"/cart/items/{BAD}", ALL, None),
    ("POST", f"/cart/items/{BAD}/ack", ALL, None),
    ("POST", "/cart/select", ALL, {}),
    ("POST", "/cart/shipto", ALL, {"postcode": 123}),  # ผิด type → 422 ไม่แตะข้อมูลจริง
    ("POST", f"/carts/{BAD}/merge", ALL, None),
    ("POST", "/cart/checkout-check", CUST, None),  # guest ชำระเงินไม่ได้ · เซลล์ห้ามรับเงินเอง
    ("POST", "/promotions/evaluate", ALL, {}),
    ("POST", f"/cart/{BAD}/discounts", ALL, {}),
    ("DELETE", f"/cart/{BAD}/discounts/{BAD}", ALL, None),
    ("POST", "/delivery/quote", ALL, {}),
    ("POST", f"/delivery/slots/{BAD}/hold", ALL, {}),
    ("POST", f"/delivery/slots/{BAD}/release", ALL, {}),
    # ---------- ดูใบเสนอราคา/ชำระเงินผ่านลิงก์ (ไม่ต้องล็อกอิน แต่ต้องมี token) ----------
    ("GET", f"/quotations/{BAD}", ALL, None),
    ("GET", f"/quotations/{BAD}/document", ALL, None),
    ("POST", f"/quotations/{BAD}/payment-intent", ALL, {}),
    ("GET", f"/payments/{BAD}", ALL, None),
    ("POST", f"/payments/{BAD}/mock-confirm", ALL, None),
    # ---------- ต้องล็อกอิน (ลูกค้าขึ้นไป) ----------
    ("GET", "/me", AUTH, None),
    ("PATCH", "/me", AUTH, {"name": 123}),  # ผิด type → 422 แต่ผ่านด่านสิทธิ์แล้ว
    # สมุดที่อยู่จัดส่ง — ใครล็อกอินก็จัดการของตัวเองได้ (service กันข้ามบัญชีด้วย 404)
    ("GET", "/me/addresses", AUTH, None),
    ("POST", "/me/addresses", AUTH, {"receiver": 123}),  # ผิด type → 422 แต่ผ่านด่านสิทธิ์แล้ว
    ("PATCH", f"/me/addresses/{BAD}", AUTH, {"receiver": 123}),
    ("POST", f"/me/addresses/{BAD}/default", AUTH, {}),
    ("DELETE", f"/me/addresses/{BAD}", AUTH, None),
    ("POST", "/events", ALL, {}),
    ("GET", "/me/recently-viewed", ALL, None),
    ("GET", "/me/wishlist", AUTH, None),
    ("POST", f"/me/wishlist/{BAD}", AUTH, None),
    ("GET", "/me/orders", AUTH, None),
    # รายการรอชำระของตัวเอง — ต้องล็อกอิน ไม่งั้นใครก็ดูของคนอื่นได้
    ("GET", "/me/pending-payments", AUTH, None),
    # ส่ง token จากปุ่ม Pay Now มาเรียก Create Charge API — ลูกค้าที่ถือลิงก์ใบนั้นเรียกได้
    ("POST", f"/payments/{BAD}/kbank/charge", ALL, None),
    ("GET", f"/me/orders/{BAD}", AUTH, None),
    ("GET", "/me/bought-again", AUTH, None),
    ("GET", "/me/privacy", AUTH, None),
    ("POST", "/me/consents", AUTH, {}),
    ("GET", "/me/data/export", AUTH, None),
    ("POST", "/me/data/delete", AUTH, {}),  # ไม่ confirm → 400 ไม่ลบจริง
    ("GET", "/presos", AUTH, None),
    ("GET", f"/presos/{BAD}", AUTH, None),
    ("GET", "/quotations", AUTH, None),
    ("POST", "/checkout/quotation", CUST, {"force": "ไม่ใช่บูลีน"}),
    # ---------- เครื่องมือเซลล์ (ลูกค้าห้ามเห็น) ----------
    ("POST", "/presos", STAFF, {}),
    ("POST", f"/presos/{BAD}/reopen", STAFF, None),
    ("POST", f"/presos/{BAD}/quotation", STAFF, {}),
    ("POST", f"/quotations/{BAD}/send", STAFF, {}),
    ("POST", f"/quotations/{BAD}/cancel", STAFF, {}),
    ("GET", "/sales/carts", STAFF, None),
    ("POST", "/sales/carts", STAFF, {"label": 12345}),  # ผิด type → 422 ไม่สร้างตะกร้าจริง
    ("GET", f"/sales/carts/{BAD}", STAFF, None),
    ("DELETE", f"/sales/carts/{BAD}", STAFF, None),
    ("POST", f"/sales/carts/{BAD}/items", STAFF, {}),
    ("PATCH", f"/sales/carts/{BAD}/items/{BAD}", STAFF, {}),
    ("DELETE", f"/sales/carts/{BAD}/items/{BAD}", STAFF, None),
    ("POST", "/sales/carts/join", STAFF, {}),   # body ไม่ครบ → 422 ไม่เข้าร่วมจริง
    ("POST", f"/sales/carts/{BAD}/attach-customer", STAFF, {}),
    ("DELETE", f"/sales/carts/{BAD}/attach-customer", STAFF, None),
    # ค่าขนส่งแบบ "เปิด Mat" — พนักงานขาย/ผู้จัดการเท่านั้น ลูกค้าแตะค่าขนส่งตัวเองไม่ได้
    # ลูกค้ากดออกจากการดูแลของพนักงานเอง — เป็นปุ่มของลูกค้า พนักงานใช้ไม่ได้
    ("DELETE", f"/cart/{BAD}/sales-owner", CUST, None),
    # ติ๊กเลือกรายการที่จะคิดเงินในใบที่พนักงานถือ — เครื่องมือของหน้าขาย
    ("POST", f"/sales/carts/{BAD}/select", STAFF, {"selected": True}),
    ("GET", f"/sales/customers/{BAD}/owner", STAFF, None),
    ("GET", "/sales/my-customers", STAFF, None),
    ("GET", "/sales/fleets", STAFF, None),
    ("GET", "/sales/delivery-extra?province=ภูเก็ต", STAFF, None),
    ("GET", f"/sales/carts/{BAD}/shipping-charge", STAFF, None),
    ("POST", f"/sales/carts/{BAD}/shipping-charge", STAFF, {"matnr": "A534", "fee": "600"}),
    ("DELETE", f"/sales/carts/{BAD}/shipping-charge", STAFF, None),
    ("POST", f"/sales/carts/{BAD}/availability", STAFF, None),
    ("POST", "/sales/availability", STAFF, {"matnr": 123}),  # ผิด type → 422 ไม่ยิง SAP จริง
    ("POST", "/sales/availability/batch", STAFF, {"items": 1}),  # ผิด type → 422 ไม่ยิง SAP จริง
    ("GET", "/customers/search?q=สม", STAFF, None),
    # ---------- หน้าพนักงานขาย: รูปตัวโชว์รายสาขา · พนักงานร่วมบิล · template ----------
    ("GET", "/staff/me", EMP, None),
    ("GET", f"/staff/materials/{BAD}/photos", EMP, None),
    ("POST", f"/staff/materials/{BAD}/photos", EMP, {}),   # ไม่ใช่ multipart → 422 ไม่สร้างรูป
    ("PUT", f"/staff/photos/{BAD}", EMP, {}),
    ("DELETE", f"/staff/photos/{BAD}", EMP, None),
    ("POST", f"/staff/photos/{BAD}/share", EMP, {"public": True}),
    ("GET", f"/materials/{BAD}/branch-photos", ALL, None),   # รูปที่แชร์แล้ว — หน้าสินค้าฝั่งลูกค้า
    ("POST", f"/quotations/{BAD}/google-sheet", EMP, None),
    ("GET", "/staff/photos/audit", MGR, None),             # AUDIT_VIEW — พนักงานขายไม่มี
    ("GET", "/staff/employees", EMP, None),
    ("GET", "/staff/roles", EMP, None),
    ("PUT", f"/sales/carts/{BAD}/staff", EMP, {"role_code": "Z1"}),
    ("PUT", f"/sales/carts/{BAD}/remark", EMP, {"overall_remark": 123}),
    ("GET", "/staff/quotation-template", EMP, None),
    ("PUT", "/staff/quotation-template", EMP, {"display_name": 123}),  # ผิด type → 422 ไม่เขียนจริง
    ("POST", "/staff/quotation-template/logo", EMP, {}),
    ("GET", f"/quotations/{BAD}/export", ALL, None),       # สิทธิ์ชุดเดียวกับหน้าเอกสาร
    # ---------- ผู้จัดการ ----------
    ("GET", "/discount-approvals", MGR, None),
    ("POST", f"/discount-approvals/{BAD}/approve", (M,), None),
    ("POST", f"/discount-approvals/{BAD}/reject", (M,), None),
    ("GET", "/admin/sap-sync", MGR, None),
    ("POST", "/admin/sap-sync/run", MGR, None),
    ("POST", f"/admin/sap-sync/{BAD}/retry", MGR, None),
    ("POST", "/admin/jobs/daily-stats", MGR, None),
    ("GET", "/admin/top-searches", MGR, None),
    ("GET", "/admin/wishlist-report", MGR, None),  # รีพอร์ตของที่ลูกค้ากดหัวใจ — ผู้จัดการ/แอดมินเท่านั้น
    ("GET", "/admin/analytics/overview", MGR, None),
    # ---------- แอดมิน ----------
    ("GET", "/admin/users", ADMIN, None),
    ("GET", "/admin/audit-logs", ADMIN, None),
    ("GET", "/admin/data-requests", ADMIN, None),
    ("POST", f"/admin/users/{BAD}/anonymize", ADMIN, {}),
    ("GET", f"/admin/users/{BAD}/data-export", ADMIN, None),
]

# โหมดทดสอบ IT — กันด้วยรหัสพนักงาน (IT_TEST_STAFF_CODES) ไม่ใช่ role ทุก role ในตารางจึงได้ 401/403
# ตัวที่ผ่านได้ทดสอบใน tests/test_step24_sales_staff.py
IT_TEST_ONLY = {("GET", "/it-test/profile"), ("PUT", "/it-test/profile")}

# endpoint ที่ไม่ได้กันด้วย role แต่กันด้วยลายเซ็น HMAC จาก payment gateway
#
# เส้นของกสิกรก็อยู่กลุ่มนี้ — ธนาคารยิงเข้ามาโดยไม่มี token ของเรา จะกันด้วย role ไม่ได้
# ด่านจริงคือการยืนยันลายเซ็น ซึ่งตอนนี้ยังทำไม่ได้ (รอสเปก) จึงยังไม่ตัดสถานะใดๆ
# ดู tests/test_step23_kbank_endpoints.py ที่เช็คว่ายิงเข้ามาแล้วใบต้องไม่กลายเป็นจ่ายแล้ว
SIGNATURE_ONLY = {
    ("POST", "/webhooks/payment"),
    ("POST", "/payment/card/notify"),
    ("POST", "/payment/qr/notify"),
    ("GET", "/payment/card/callback"),
    ("POST", "/payment/card/callback"),
    ("GET", "/payment/kbank/status"),
}

# ผูกเลขสมาชิก — ตารางนี้เช็คได้แค่ "role ไหนเข้าได้" แต่ด่านจริงของกลุ่มนี้คือ
# "ยืนยันเบอร์ด้วย OTP แล้วหรือยัง" ซึ่งลูกค้าที่ล็อกอินด้วยรหัสผ่านก็ยังโดน 403
# จึงใส่ตารางนี้ไม่ได้ (จะขัดกับกฎ "role ที่อนุญาตต้องไม่ได้ 401/403")
# ความปลอดภัยทั้งชุดคุมด้วย tests/test_step14_auth_security.py แทน
PHONE_VERIFIED_ONLY = {
    ("GET", "/me/member/candidates"),
    ("POST", "/me/member/lookup"),
    ("POST", "/me/member/otp"),
    ("POST", "/me/member/link"),
    ("DELETE", "/me/member/link"),
}

STAFF_LOGIN = {S: ("SA-104", "staff"), M: ("MG-001", "staff"), A: ("ADM-001", "staff"), C: ("1100440182", "customer")}


@pytest.fixture(scope="module", autouse=True)
def _seed():
    ensure_seed()


def _headers(client, role: str) -> dict:
    if role == G:
        return {}
    ident, kind = STAFF_LOGIN[role]
    return auth_headers(client, ident, kind)


def _call(client, method: str, path: str, headers: dict, body):
    kw = {"headers": headers}
    if method in ("POST", "PATCH", "PUT"):
        kw["json"] = body if body is not None else {}
    return client.request(method, path, **kw)


@pytest.mark.parametrize("method,path,allowed,body", MATRIX, ids=[f"{m} {p}" for m, p, _, _ in MATRIX])
def test_permission_matrix(client, method, path, allowed, body):
    for role in ALL:
        r = _call(client, method, path, _headers(client, role), body)
        if role in allowed:
            assert r.status_code not in (401, 403), f"{role} ควรเข้าถึง {method} {path} ได้ แต่ได้ {r.status_code}: {r.text[:200]}"
        else:
            assert r.status_code in (401, 403), f"{role} ไม่ควรเข้าถึง {method} {path} แต่ได้ {r.status_code}: {r.text[:200]}"


def test_matrix_covers_every_endpoint():
    """กันลืม: endpoint ใหม่ที่ยังไม่มีในตารางต้องทำให้ test พัง"""
    covered = {(m, p.split("?")[0]) for m, p, _, _ in MATRIX} | SIGNATURE_ONLY | PHONE_VERIFIED_ONLY | IT_TEST_ONLY
    covered = {(m, p.replace(BAD, "{}")) for m, p in covered}
    actual = set()
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            # แทน path param ด้วย {} เพื่อเทียบกับตารางที่ใส่ค่าจริงลงไปแล้ว
            norm = "/".join("{}" if seg.startswith("{") else seg for seg in path.split("/"))
            actual.add((method.upper(), norm))
    assert not actual - covered, f"endpoint ที่ยังไม่มีใน matrix: {sorted(actual - covered)}"


def test_webhook_needs_signature_for_everyone(client):
    """webhook ไม่ได้กันด้วย role — ทุกคนรวมทั้งแอดมินต้องมีลายเซ็นถูกต้องเท่านั้น"""
    for role in ALL:
        r = client.post("/webhooks/payment", json={"payment_no": BAD}, headers=_headers(client, role))
        assert r.status_code in (400, 401), f"{role}: {r.status_code} {r.text[:200]}"


def test_closed_cart_revokes_sales_access(client):
    """ปิดตะกร้า/จบเซสชัน → เซลล์เข้าถึงไม่ได้อีก"""
    sales = auth_headers(client, "SA-105", "staff")
    cart_id = client.post("/sales/carts", json={"label": "ทดสอบสิทธิ์"}, headers=sales).json()["id"]
    assert client.get(f"/sales/carts/{cart_id}", headers=sales).status_code == 200

    assert client.delete(f"/sales/carts/{cart_id}", headers=sales).status_code == 200
    # ปิดแล้วต้องหมดสิทธิ์ทันที ทั้งอ่านและเขียน
    assert client.get(f"/sales/carts/{cart_id}", headers=sales).status_code == 403
    assert client.post(f"/sales/carts/{cart_id}/items", json={"matnr": "10023841", "qty": 1}, headers=sales).status_code == 403
    assert client.delete(f"/sales/carts/{cart_id}", headers=sales).status_code == 403
    assert cart_id not in [c["id"] for c in client.get("/sales/carts", headers=sales).json()]


def test_other_sales_cannot_touch_my_cart(client):
    """ตะกร้าของเซลล์คนหนึ่ง เซลล์อีกคนเข้าไม่ได้แม้ยังเปิดอยู่"""
    a = auth_headers(client, "SA-104", "staff")
    b = auth_headers(client, "SA-105", "staff")
    cart_id = client.post("/sales/carts", json={"label": "ของ SA-104"}, headers=a).json()["id"]
    try:
        assert client.get(f"/sales/carts/{cart_id}", headers=b).status_code == 403
        assert client.post(f"/sales/carts/{cart_id}/items", json={"matnr": "10023841", "qty": 1}, headers=b).status_code == 403
    finally:
        client.delete(f"/sales/carts/{cart_id}", headers=a)
