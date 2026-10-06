"""สิทธิ์ของพนักงาน — โค้ดธุรกิจเช็คด้วย "สิทธิ์" ไม่ใช่ "ชื่อบทบาท"

ทำไมไม่เขียน `if role == "manager"` ในโค้ด: วันที่ Employee Login API จริงมา สิทธิ์จะมาจาก
ระบบนั้นเป็นรายการ (หรือบทบาทชื่ออื่นที่เราไม่รู้จัก) · ถ้าโค้ดผูกกับชื่อบทบาท ต้องไล่แก้ทุกที่
ถ้าผูกกับสิทธิ์ แก้แค่ตารางข้างล่าง (หรือเลิกใช้ตารางแล้วอ่านจาก API) ที่เดียวจบ

ตาราง ROLE_PERMISSIONS เป็นของชั่วคราวระหว่างรอ API — ดู services/employee_provider.py
"""

# ---------- รูปสินค้าตัวโชว์รายสาขา ----------
PRODUCT_IMAGE_CREATE = "PRODUCT_IMAGE_CREATE"
PRODUCT_IMAGE_READ = "PRODUCT_IMAGE_READ"
PRODUCT_IMAGE_UPDATE_OWN = "PRODUCT_IMAGE_UPDATE_OWN"
PRODUCT_IMAGE_DELETE_OWN = "PRODUCT_IMAGE_DELETE_OWN"
PRODUCT_IMAGE_UPDATE_ALL = "PRODUCT_IMAGE_UPDATE_ALL"
PRODUCT_IMAGE_DELETE_ALL = "PRODUCT_IMAGE_DELETE_ALL"
PRODUCT_IMAGE_VIEW_ALL_BRANCH = "PRODUCT_IMAGE_VIEW_ALL_BRANCH"
PRODUCT_IMAGE_AUDIT_VIEW = "PRODUCT_IMAGE_AUDIT_VIEW"

# ---------- ใบเสนอราคา / ตะกร้า ----------
QUOTATION_TEMPLATE_OWN = "QUOTATION_TEMPLATE_OWN"   # จัดการ template ของตัวเอง
CART_STAFF_ASSIGN = "CART_STAFF_ASSIGN"             # ใส่พนักงานร่วมบิล Z1-ZK

_SALES = frozenset({
    PRODUCT_IMAGE_CREATE, PRODUCT_IMAGE_READ,
    PRODUCT_IMAGE_UPDATE_OWN, PRODUCT_IMAGE_DELETE_OWN,
    QUOTATION_TEMPLATE_OWN, CART_STAFF_ASSIGN,
})
_MANAGER = _SALES | {
    PRODUCT_IMAGE_UPDATE_ALL, PRODUCT_IMAGE_DELETE_ALL, PRODUCT_IMAGE_AUDIT_VIEW,
}
_ADMIN = _MANAGER | {PRODUCT_IMAGE_VIEW_ALL_BRANCH}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "sales": _SALES,
    "manager": frozenset(_MANAGER),
    "admin": frozenset(_ADMIN),
}


def permissions_for_role(role: str) -> frozenset[str]:
    """บทบาทที่ไม่รู้จัก = ไม่มีสิทธิ์อะไรเลย (ไม่ใช่ได้สิทธิ์ตั้งต้นของพนักงานขาย)
    เผื่อวันที่ API ส่งบทบาทชื่อใหม่มา จะได้ปิดไว้ก่อนแทนที่จะเปิดโดยไม่ตั้งใจ"""
    return ROLE_PERMISSIONS.get(role, frozenset())
