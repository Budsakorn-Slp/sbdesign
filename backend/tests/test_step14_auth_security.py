"""STEP 14 — ความปลอดภัยการล็อกอิน + ผูกเลขสมาชิก

โจทย์หลักที่เทสชุดนี้กัน: เลขสมาชิกเป็น "ตัวระบุ" ไม่ใช่ "ความลับ" (พิมพ์อยู่บนใบเสร็จ)
ใครก็เอาเลขของคนอื่นมาผูกเข้าบัญชีตัวเองได้ถ้าไม่บังคับพิสูจน์การถือเบอร์
"""
import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.user import AuthAttempt, OtpCode, User
from tests.helpers import auth_headers, ensure_seed

# ลูกค้าในทะเบียนสมาชิกจำลอง (seed/sap_mock/customers.json)
MEMBER_NO = "1100440205"
MEMBER_PHONE = "0812223333"
OTHER_NO = "1100440310"
OTHER_PHONE = "022345678"


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        # ตัวนับ rate limit ค้างจากเทสก่อนหน้าจะทำให้เทสถัดไปโดน 429 — ล้างก่อนทุกครั้ง
        db.execute(delete(AuthAttempt))
        db.execute(delete(OtpCode))
        db.commit()


def _otp_login(client, phone: str, name: str | None = None) -> dict:
    """ล็อกอินด้วย OTP แล้วคืน header — ผ่าน OTP = เบอร์ถูกพิสูจน์แล้ว"""
    code = client.post("/auth/otp/request", json={"phone": phone}).json()["debug_code"]
    r = client.post("/auth/otp/verify", json={"phone": phone, "code": code, "name": name})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def _unlink_all(sap_no: str) -> None:
    with SessionLocal() as db:
        for u in db.scalars(select(User).where(User.sap_customer_no == sap_no)):
            u.sap_customer_no, u.points = None, 0
        db.commit()


# ---------- ล็อกอิน ----------

def test_login_locks_out_after_repeated_failures(client):
    for _ in range(5):
        r = client.post("/auth/login", json={"identifier": "SA-104", "password": "ผิดแน่ๆ", "account_type": "staff"})
        assert r.status_code == 401
    # ครั้งที่ 6 ต้องโดนกั้น ไม่ใช่ 401 เฉยๆ — ไม่งั้นไล่เดารหัสได้ไม่จำกัด
    blocked = client.post("/auth/login", json={"identifier": "SA-104", "password": "ผิดแน่ๆ", "account_type": "staff"})
    assert blocked.status_code == 429
    # และรหัสที่ถูกต้องก็ต้องโดนกั้นด้วยในช่วงล็อก (ไม่งั้นการล็อกไม่มีความหมาย)
    assert client.post("/auth/login", json={"identifier": "SA-104", "password": "1122", "account_type": "staff"}).status_code == 429


def test_login_error_does_not_reveal_whether_account_exists(client):
    a = client.post("/auth/login", json={"identifier": "SA-104", "password": "ผิด", "account_type": "staff"})
    b = client.post("/auth/login", json={"identifier": "SA-999", "password": "ผิด", "account_type": "staff"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


# ---------- OTP ----------

def test_otp_is_not_stored_in_plain_text(client):
    body = client.post("/auth/otp/request", json={"phone": MEMBER_PHONE}).json()
    code = body["debug_code"]
    assert body["phone"] != MEMBER_PHONE and "xxx" in body["phone"]  # ตอบกลับต้องปิดบังเบอร์
    with SessionLocal() as db:
        otp = db.scalar(select(OtpCode).where(OtpCode.phone == MEMBER_PHONE))
        assert otp is not None and code not in otp.code_hash and len(otp.code_hash) == 64


def test_otp_dies_after_too_many_wrong_attempts(client):
    client.post("/auth/otp/request", json={"phone": MEMBER_PHONE})
    for _ in range(5):
        assert client.post("/auth/otp/verify", json={"phone": MEMBER_PHONE, "code": "000000"}).status_code == 400
    with SessionLocal() as db:
        assert db.scalar(select(OtpCode).where(OtpCode.phone == MEMBER_PHONE)).used is True


def test_otp_cannot_be_reused(client):
    code = client.post("/auth/otp/request", json={"phone": MEMBER_PHONE}).json()["debug_code"]
    assert client.post("/auth/otp/verify", json={"phone": MEMBER_PHONE, "code": code}).status_code == 200
    assert client.post("/auth/otp/verify", json={"phone": MEMBER_PHONE, "code": code}).status_code == 400


def test_asking_for_a_new_otp_kills_the_previous_one(client):
    first = client.post("/auth/otp/request", json={"phone": MEMBER_PHONE}).json()["debug_code"]
    with SessionLocal() as db:  # ข้าม cooldown 60 วิ โดยลบร่องรอยการส่งครั้งแรก
        db.execute(delete(AuthAttempt))
        db.commit()
    second = client.post("/auth/otp/request", json={"phone": MEMBER_PHONE}).json()["debug_code"]
    assert client.post("/auth/otp/verify", json={"phone": MEMBER_PHONE, "code": first}).status_code == 400
    assert client.post("/auth/otp/verify", json={"phone": MEMBER_PHONE, "code": second}).status_code == 200


def test_otp_resend_has_a_cooldown(client):
    assert client.post("/auth/otp/request", json={"phone": MEMBER_PHONE}).status_code == 200
    assert client.post("/auth/otp/request", json={"phone": MEMBER_PHONE}).status_code == 429


# ---------- ผูกเลขสมาชิก ----------

def test_verified_phone_finds_its_own_membership(client):
    _unlink_all(MEMBER_NO)
    h = _otp_login(client, MEMBER_PHONE)
    rows = client.get("/me/member/candidates", headers=h).json()
    assert len(rows) == 1
    row = rows[0]
    assert row["sap_customer_no"] == MEMBER_NO and row["can_link_now"] is True
    # ข้อมูลติดต่อต้องปิดบัง ตอนนี้ยังไม่ได้พิสูจน์ว่าเป็นเจ้าของรายนี้
    assert MEMBER_PHONE not in row["phone_masked"] and "xxx" in row["phone_masked"]


def test_link_succeeds_when_phone_matches(client):
    _unlink_all(MEMBER_NO)
    h = _otp_login(client, MEMBER_PHONE)
    r = client.post("/me/member/link", json={"sap_customer_no": MEMBER_NO}, headers=h)
    assert r.status_code == 200 and r.json()["points"] == 340
    assert client.get("/me", headers=h).json()["sap_customer_no"] == MEMBER_NO


def test_link_takes_the_name_from_the_member_registry(client):
    """ผูกแล้วชื่อต้องเป็นชื่อจากทะเบียน แม้ลูกค้าจะเคยตั้งชื่อเองไว้

    เพราะหลังผูกหน้าเว็บล็อกไม่ให้แก้ชื่อแล้ว (ชื่อไปอยู่บนเอกสารที่ออกจาก SAP)
    ถ้าปล่อยชื่อที่ลูกค้าพิมพ์ไว้ จะล็อกชื่อที่ไม่ตรงกับเอกสารจริง
    """
    _unlink_all(MEMBER_NO)
    h = _otp_login(client, MEMBER_PHONE)
    # ยังไม่ผูก = ตั้งชื่อเองได้ (ชื่อบัญชีเฉยๆ ยังไม่ไปอยู่บนเอกสารอะไร)
    assert client.patch("/me", json={"name": "ชื่อเล่นที่ตั้งเอง"}, headers=h).status_code == 200
    assert client.get("/me", headers=h).json()["name"] == "ชื่อเล่นที่ตั้งเอง"

    r = client.post("/me/member/link", json={"sap_customer_no": MEMBER_NO}, headers=h)
    assert r.status_code == 200
    registry_name = r.json()["name"]
    assert client.get("/me", headers=h).json()["name"] == registry_name != "ชื่อเล่นที่ตั้งเอง"

    # ผูกแล้วแก้ชื่อเองไม่ได้อีก
    assert client.patch("/me", json={"name": "ขอเปลี่ยนกลับ"}, headers=h).status_code == 409


def test_cannot_hijack_someone_elses_membership_by_typing_the_number(client):
    """หัวใจของชุดนี้ — รู้เลขสมาชิกคนอื่นแล้วผูกเข้าบัญชีตัวเองไม่ได้"""
    _unlink_all(OTHER_NO)
    h = _otp_login(client, "0899999001", name="คนแปลกหน้า")
    r = client.post("/me/member/link", json={"sap_customer_no": OTHER_NO}, headers=h)
    assert r.status_code == 401  # ต้องยืนยัน OTP ที่เบอร์ของสมาชิกรายนั้นก่อน
    with SessionLocal() as db:
        assert db.scalar(select(User).where(User.sap_customer_no == OTHER_NO)) is None


def test_lookup_says_otp_needed_without_leaking_the_phone(client):
    _unlink_all(OTHER_NO)
    h = _otp_login(client, "0899999002", name="คนแปลกหน้า")
    body = client.post("/me/member/lookup", json={"sap_customer_no": OTHER_NO}, headers=h).json()
    assert body["requires_otp"] is True
    assert OTHER_PHONE not in body["member"]["phone_masked"]


def test_step_up_otp_goes_to_the_member_phone_and_completes_the_link(client):
    """เคสจริง: ลูกค้าเปลี่ยนเบอร์ใหม่ แต่ยังถือเบอร์เดิมที่ผูกกับสมาชิกอยู่"""
    _unlink_all(OTHER_NO)
    h = _otp_login(client, "0899999003", name="ลูกค้าเบอร์ใหม่")
    sent = client.post("/me/member/otp", json={"sap_customer_no": OTHER_NO}, headers=h)
    assert sent.status_code == 200 and OTHER_PHONE not in sent.json()["phone"]
    code = sent.json()["debug_code"]
    r = client.post("/me/member/link", json={"sap_customer_no": OTHER_NO, "otp_code": code}, headers=h)
    assert r.status_code == 200 and r.json()["sap_customer_no"] == OTHER_NO


def test_link_otp_cannot_be_used_for_a_different_member(client):
    """รหัสที่ขอไว้สำหรับสมาชิกใบหนึ่ง เอาไปผูกอีกใบไม่ได้"""
    _unlink_all(OTHER_NO)
    _unlink_all(MEMBER_NO)
    h = _otp_login(client, "0899999004", name="คนแปลกหน้า")
    code = client.post("/me/member/otp", json={"sap_customer_no": OTHER_NO}, headers=h).json()["debug_code"]
    r = client.post("/me/member/link", json={"sap_customer_no": MEMBER_NO, "otp_code": code}, headers=h)
    assert r.status_code in (400, 401)


def test_a_membership_cannot_be_linked_to_two_accounts(client):
    _unlink_all(MEMBER_NO)
    owner = _otp_login(client, MEMBER_PHONE)
    assert client.post("/me/member/link", json={"sap_customer_no": MEMBER_NO}, headers=owner).status_code == 200
    other = _otp_login(client, "0899999005", name="คนที่สอง")
    r = client.post("/me/member/lookup", json={"sap_customer_no": MEMBER_NO}, headers=other)
    assert r.status_code == 404  # ตอบเหมือนเลขไม่มีจริง ไม่บอกว่า "ถูกใครผูกไปแล้ว"


def test_password_only_account_cannot_link_without_verifying_phone(client):
    """สมัครด้วยรหัสผ่านเฉยๆ ยังไม่นับว่าพิสูจน์เบอร์ — ผูกไม่ได้จนกว่าจะยืนยัน OTP"""
    _unlink_all(MEMBER_NO)
    h = auth_headers(client, "094-916-4600")
    r = client.post("/me/member/link", json={"sap_customer_no": MEMBER_NO}, headers=h)
    assert r.status_code == 403


def test_unlink_clears_the_number_and_points(client):
    _unlink_all(MEMBER_NO)
    h = _otp_login(client, MEMBER_PHONE)
    client.post("/me/member/link", json={"sap_customer_no": MEMBER_NO}, headers=h)
    assert client.delete("/me/member/link", headers=h).status_code == 204
    me = client.get("/me", headers=h).json()
    assert me["sap_customer_no"] is None and me["points"] == 0


def test_staff_cannot_link_a_membership(client):
    h = auth_headers(client, "SA-104", "staff")
    assert client.post("/me/member/link", json={"sap_customer_no": MEMBER_NO}, headers=h).status_code == 403


def test_member_endpoints_require_login(client):
    """ทุกด่านของการผูกสมาชิกต้องล็อกอินก่อน — ไม่มีทางเรียกแบบไม่ระบุตัวตน"""
    calls = [
        ("GET", "/me/member/candidates", None),
        ("POST", "/me/member/lookup", {"sap_customer_no": MEMBER_NO}),
        ("POST", "/me/member/otp", {"sap_customer_no": MEMBER_NO}),
        ("POST", "/me/member/link", {"sap_customer_no": MEMBER_NO}),
        ("DELETE", "/me/member/link", None),
    ]
    for method, path, body in calls:
        kw = {"json": body} if body is not None else {}
        r = client.request(method, path, **kw)
        assert r.status_code in (401, 403), f"{method} {path} -> {r.status_code}"


# ---------- ลืมรหัสผ่าน / ตั้งรหัสใหม่ ----------

def test_password_reset_with_otp_then_login_with_new_password(client):
    phone = "0899999010"
    client.post("/auth/otp/request", json={"phone": phone})
    code = client.post("/auth/otp/request", json={"phone": phone}).json().get("debug_code")
    # เบอร์ใหม่: สร้างบัญชีผ่าน OTP ก่อน แล้วค่อยตั้งรหัสผ่าน
    with SessionLocal() as db:
        db.execute(delete(AuthAttempt))
        db.commit()
    code = client.post("/auth/otp/request", json={"phone": phone}).json()["debug_code"]
    client.post("/auth/otp/verify", json={"phone": phone, "code": code, "name": "ลูกค้าลืมรหัส"})

    with SessionLocal() as db:
        db.execute(delete(AuthAttempt))
        db.commit()
    reset_code = client.post("/auth/password/forgot", json={"phone": phone}).json()["debug_code"]
    r = client.post("/auth/password/reset", json={"phone": phone, "code": reset_code, "new_password": "n3wpass"})
    assert r.status_code == 200 and r.json()["user"]["phone"] == phone

    with SessionLocal() as db:
        db.execute(delete(AuthAttempt))
        db.commit()
    ok = client.post("/auth/login", json={"identifier": phone, "password": "n3wpass", "account_type": "customer"})
    assert ok.status_code == 200


def test_login_otp_cannot_be_used_to_reset_a_password(client):
    """รหัสที่ขอไว้เพื่อ "เข้าระบบ" ต้องเอาไปเปลี่ยนรหัสผ่านไม่ได้ — คนละเจตนา"""
    phone = "0899999011"
    login_code = client.post("/auth/otp/request", json={"phone": phone}).json()["debug_code"]
    r = client.post("/auth/password/reset", json={"phone": phone, "code": login_code, "new_password": "hack1234"})
    assert r.status_code == 400


def test_password_reset_answers_the_same_for_unknown_numbers(client):
    """ตอบเหมือนกันไม่ว่าเบอร์นั้นจะมีบัญชีหรือไม่ — ไม่ให้ใช้ไล่เช็คว่าใครเป็นลูกค้า"""
    known = client.post("/auth/password/forgot", json={"phone": "0812223333"})
    with SessionLocal() as db:
        db.execute(delete(AuthAttempt))
        db.commit()
    unknown = client.post("/auth/password/forgot", json={"phone": "0898888001"})
    assert known.status_code == unknown.status_code == 200
    assert known.json()["sent"] == unknown.json()["sent"] is True


def test_password_reset_kicks_out_other_devices(client):
    """ตั้งรหัสใหม่ = ตัด session อื่นทิ้ง เผื่อกรณีโดนคนอื่นเข้าบัญชีไปก่อนหน้า"""
    phone = "0899999012"
    code = client.post("/auth/otp/request", json={"phone": phone}).json()["debug_code"]
    old = client.post("/auth/otp/verify", json={"phone": phone, "code": code, "name": "ทดสอบ"}).json()

    with SessionLocal() as db:
        db.execute(delete(AuthAttempt))
        db.commit()
    reset_code = client.post("/auth/password/forgot", json={"phone": phone}).json()["debug_code"]
    client.post("/auth/password/reset", json={"phone": phone, "code": reset_code, "new_password": "afterreset"})

    # refresh token ของเครื่องเดิมต้องใช้ไม่ได้แล้ว
    assert client.post("/auth/refresh", json={"refresh_token": old["refresh_token"]}).status_code == 401


# ---------- ตั้งค่าบัญชีหลังล็อกอินครั้งแรก (STEP 17) ----------

def test_new_otp_account_is_asked_to_set_up_once_and_never_again(client):
    """บั๊กเดิม: คนที่ไม่มีบัตรสมาชิกเจอหน้า "ตั้งค่าบัญชี" ทุกครั้งที่ล็อกอิน

    เพราะหน้าเว็บใช้เงื่อนไข "ยังไม่มี sap_customer_no" ซึ่งเป็นจริงของเขาตลอดไป
    ตอนนี้ต้องจำว่าเคยผ่าน/เคยข้ามไปแล้ว แม้จะข้ามโดยไม่กรอกอะไรเลยก็ตาม
    """
    phone = "0899990101"
    hs = _otp_login(client, phone)
    assert client.get("/me", headers=hs).json()["needs_profile"] is True

    # กด "ข้ามไปก่อน" — ไม่กรอกอะไรเลย แต่ต้องไม่ถูกถามอีก
    assert client.patch("/me", json={"onboarded": True}, headers=hs).json()["needs_profile"] is False

    with SessionLocal() as db:
        db.execute(delete(AuthAttempt))
        db.execute(delete(OtpCode))
        db.commit()
    again = _otp_login(client, phone)
    assert client.get("/me", headers=again).json()["needs_profile"] is False


def test_profile_step_saves_name_email_and_optional_password(client):
    phone = "0899990102"
    hs = _otp_login(client, phone)
    r = client.patch("/me", json={"name": "ณภัทร พงษ์ศรี", "email": "Napat@Example.com", "password": "supersecret", "onboarded": True}, headers=hs)
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["name"] == "ณภัทร พงษ์ศรี" and me["email"] == "napat@example.com" and me["needs_profile"] is False
    # ตั้งรหัสแล้วต้องเข้าด้วยรหัสผ่านได้จริง ไม่ใช่แค่บันทึกลง DB เฉยๆ
    assert client.post("/auth/login", json={"identifier": phone, "password": "supersecret"}).status_code == 200


def test_profile_step_refuses_an_email_that_belongs_to_someone_else(client):
    """email เป็น unique ใน DB — ถ้าไม่ดักจะได้ 500 แทนข้อความที่ลูกค้าอ่านรู้เรื่อง"""
    first = _otp_login(client, "0899990103")
    client.patch("/me", json={"email": "taken@example.com", "onboarded": True}, headers=first)
    with SessionLocal() as db:
        db.execute(delete(AuthAttempt))
        db.execute(delete(OtpCode))
        db.commit()
    second = _otp_login(client, "0899990104")
    assert client.patch("/me", json={"email": "TAKEN@example.com"}, headers=second).status_code == 409


def test_existing_password_cannot_be_overwritten_through_the_profile_endpoint(client):
    """session ที่ถูกขโมยไปต้องยึดบัญชีด้วยการตั้งรหัสทับไม่ได้ — ต้องไปทางยืนยัน OTP"""
    phone = "0899990105"
    hs = _otp_login(client, phone)
    assert client.patch("/me", json={"password": "firstpassword"}, headers=hs).status_code == 200
    assert client.patch("/me", json={"password": "hijacked1"}, headers=hs).status_code == 409
    assert client.post("/auth/login", json={"identifier": phone, "password": "firstpassword"}).status_code == 200


def test_linking_a_member_skips_the_profile_step_entirely(client):
    """ผูกบัตรสมาชิกแล้ว = ได้ชื่อ/อีเมลจากทะเบียนมาแล้ว ไม่ต้องถามซ้ำ"""
    _unlink_all(MEMBER_NO)
    hs = _otp_login(client, MEMBER_PHONE)
    assert client.post("/me/member/link", json={"sap_customer_no": MEMBER_NO}, headers=hs).status_code == 200
    assert client.get("/me", headers=hs).json()["needs_profile"] is False
