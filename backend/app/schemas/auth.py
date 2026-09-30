from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: str
    role: str
    name: str
    phone: str | None = None
    email: str | None = None
    sap_customer_no: str | None = None
    staff_code: str | None = None
    branch_id: str | None = None
    points: int = 0
    is_guest: bool = False
    default_address: str | None = None
    default_postcode: str | None = None
    # ที่อยู่ในทะเบียนสมาชิก (SAP) — อ่านอย่างเดียว ใช้โชว์คู่กับสมุดที่อยู่จัดส่ง
    sap_address: str | None = None
    sap_postcode: str | None = None
    has_password: bool = False
    # หน้าเว็บใช้ตัวนี้ตัดสินว่าจะพาไปหน้าตั้งค่าบัญชีต่อไหม (ดู User.needs_profile)
    needs_profile: bool = False

    model_config = {"from_attributes": True}


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class RegisterIn(BaseModel):
    phone: str = Field(min_length=9, max_length=20)
    password: str = Field(min_length=4, max_length=72)
    name: str = Field(min_length=1, max_length=120)
    email: str | None = None


class LoginIn(BaseModel):
    identifier: str = Field(min_length=1, description="ลูกค้า: เบอร์โทร / อีเมล / เลขสมาชิก · พนักงาน: รหัสพนักงาน")
    password: str = Field(min_length=1)
    account_type: str = Field(default="customer", pattern="^(customer|staff)$")


class RefreshIn(BaseModel):
    refresh_token: str


class OtpRequestIn(BaseModel):
    phone: str = Field(min_length=9, max_length=20)


class OtpVerifyIn(BaseModel):
    phone: str
    code: str = Field(min_length=4, max_length=8)
    name: str | None = None


class AddressIn(BaseModel):
    """ที่อยู่จัดส่งหนึ่งใบในสมุดที่อยู่ — ตอนแก้ไขส่งมาเฉพาะช่องที่เปลี่ยนก็ได้"""

    label: str | None = Field(default=None, max_length=40)       # บ้าน · ที่ทำงาน
    receiver: str | None = Field(default=None, max_length=120)   # ชื่อผู้รับ
    phone: str | None = Field(default=None, max_length=32)
    address: str | None = None                                   # เลขที่ หมู่บ้าน ตึก ถนน ซอย
    sub: str | None = Field(default=None, max_length=120)        # แขวง/ตำบล
    district: str | None = Field(default=None, max_length=120)   # เขต/อำเภอ
    province: str | None = Field(default=None, max_length=120)
    postcode: str | None = Field(default=None, max_length=8)
    note: str | None = Field(default=None, max_length=200)       # จุดสังเกต
    is_default: bool | None = None


class AddressOut(BaseModel):
    id: str
    label: str | None = None
    receiver: str = ""
    phone: str = ""
    address: str = ""
    sub: str | None = None
    district: str | None = None
    province: str | None = None
    postcode: str = ""
    note: str | None = None
    is_default: bool = False
    one_line: str = ""

    model_config = {"from_attributes": True}


class ProfileIn(BaseModel):
    """แก้ข้อมูลของตัวเอง (ที่อยู่แก้ผ่านหน้า checkout)

    ทุกฟิลด์เป็น optional เพราะหน้า "ตั้งค่าบัญชี" หลังล็อกอินครั้งแรกส่งมาไม่ครบเสมอ —
    บังคับแค่ชื่อ ส่วนอีเมล/รหัสผ่านลูกค้าเลือกกรอกหรือข้ามก็ได้ (เข้าระบบด้วย OTP ได้อยู่แล้ว)
    ฟิลด์ที่ไม่ส่งมา = ไม่แตะของเดิม ส่วนส่งมาเป็น "" = ล้างค่า (เฉพาะอีเมล)
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=160)
    password: str | None = Field(default=None, min_length=8, max_length=72)
    # ผู้ใช้กดจบขั้นตั้งค่าบัญชีแล้ว (กรอกครบหรือกดข้ามก็ตาม) → เลิกถามครั้งต่อไป
    onboarded: bool = False


class PasswordForgotIn(BaseModel):
    phone: str = Field(min_length=9, max_length=20)


class PasswordResetIn(BaseModel):
    phone: str = Field(min_length=9, max_length=20)
    code: str = Field(min_length=4, max_length=8)
    new_password: str = Field(min_length=4, max_length=72)


# ---------- ผูกเลขสมาชิก (SAP customer) ----------
class MemberCardOut(BaseModel):
    """ข้อมูลสมาชิกเท่าที่ยอมให้เห็นก่อนพิสูจน์ตัวตน — เบอร์/อีเมลปิดบังเสมอ"""

    sap_customer_no: str
    name: str
    points: int = 0
    phone_masked: str
    email_masked: str | None = None
    can_link_now: bool = False


class MemberLinkIn(BaseModel):
    sap_customer_no: str = Field(min_length=1, max_length=32)
    # ต้องใส่เมื่อเบอร์ในทะเบียนสมาชิกไม่ตรงกับเบอร์ที่ยืนยันไว้ (ดู start_link → requires_otp)
    otp_code: str | None = Field(default=None, min_length=4, max_length=8)


class MemberLookupIn(BaseModel):
    sap_customer_no: str = Field(min_length=1, max_length=32)


class MemberLinkStartOut(BaseModel):
    sap_customer_no: str
    requires_otp: bool
    member: MemberCardOut


class MemberLinkedOut(BaseModel):
    sap_customer_no: str
    name: str
    points: int
    linked_at: str
