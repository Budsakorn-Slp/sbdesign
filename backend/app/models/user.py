from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, utcnow, uuid_pk

ROLES = ("customer", "sales", "manager", "admin")


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = uuid_pk()
    role: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # customer|sales|manager|admin
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    # เบอร์นี้พิสูจน์ด้วย OTP แล้วหรือยัง — สมัครด้วยรหัสผ่านเฉยๆ ยังไม่นับว่าพิสูจน์
    # ใช้เป็นเงื่อนไขของการผูกเลขสมาชิก: ไม่มีการพิสูจน์เบอร์ = ผูกไม่ได้
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    email: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    sap_customer_no: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    staff_code: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    branch_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # แต้มสะสม — SAP เป็นเจ้าของตัวเลขจริง ฝั่งนี้เก็บไว้โชว์เฉยๆ อัปเดตตอน login/ผูกลูกค้า
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_postcode: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # ที่อยู่ในทะเบียนสมาชิกฝั่ง SAP — คนละอย่างกับสมุดที่อยู่จัดส่ง (user_addresses)
    # อันนี้คือที่อยู่ที่ลูกค้าให้ไว้ตอนสมัครสมาชิกที่สาขา SAP เป็นเจ้าของ แก้บนเว็บไม่ได้
    # (ใช้อ้างอิง/ออกเอกสาร) ส่วนจะส่งของไปที่ไหนให้เลือกจากสมุดที่อยู่
    sap_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    sap_postcode: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # PDPA — ความยินยอมการตลาด (ค่าเริ่มต้น "ไม่ยินยอม") + วันที่ลบตัวตนตามคำขอ
    consent_marketing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_marketing_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # ผ่านขั้น "ตั้งค่าบัญชี" หลังล็อกอินครั้งแรกแล้ว (จะกรอกครบหรือกดข้ามก็นับ)
    # เก็บไว้เพื่อไม่ให้ถามซ้ำทุกครั้งที่ล็อกอิน — ดู needs_profile
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    addresses: Mapped[list["UserAddress"]] = relationship(back_populates="user", cascade="all, delete-orphan",
                                                          order_by="UserAddress.created_at")

    @property
    def is_staff(self) -> bool:
        return self.role in ("sales", "manager", "admin")

    @property
    def has_password(self) -> bool:
        """ตั้งรหัสผ่านไว้แล้วหรือยัง — หน้าเว็บใช้ซ่อนช่อง "ตั้งรหัสผ่าน" ที่กดแล้วจะได้ 409
        ส่งออกแค่ true/false ไม่ใช่ตัว hash"""
        return bool(self.password_hash)

    @property
    def needs_profile(self) -> bool:
        """ควรพาไปหน้าตั้งค่าบัญชีหลังล็อกอินไหม

        ผูกเลขสมาชิกแล้ว = ไม่ต้องถาม เพราะชื่อ/อีเมล/ที่อยู่ดึงมาจากทะเบียนได้หมดแล้ว
        ที่เหลือถามครั้งเดียว: กดข้ามก็ปิดถาวร (ไปแก้เองได้ที่หน้าบัญชี) — เงื่อนไขเดิม
        ที่ดูแค่ "ยังไม่มีเลขสมาชิก" เป็นจริงตลอดไปสำหรับคนที่ไม่มีบัตร จึงเด้งซ้ำไม่จบ
        """
        return self.role == "customer" and not self.is_guest and self.onboarded_at is None and not self.sap_customer_no


class UserAddress(Base, TimestampMixin):
    """สมุดที่อยู่ของลูกค้า — เก็บได้หลายที่อยู่แล้วเลือกตอนสั่งซื้อ (บ้าน/ที่ทำงาน/ส่งให้คนอื่น)

    ของเดิมมีที่เก็บช่องเดียว (users.default_address) ลูกค้าที่สลับที่อยู่ประจำต้องพิมพ์ใหม่ทุกครั้ง
    ค่าส่งคิดจากรหัสไปรษณีย์ การพิมพ์ผิดจึงไม่ใช่แค่ความรำคาญ แต่ทำให้ค่าส่งผิดเขตไปเลย

    ที่อยู่นี้ใช้สำหรับ "ส่งของ" เท่านั้น ไม่ใช่ที่อยู่ใบกำกับภาษี (ใบกำกับภาษีถามแยกตอนสั่งซื้อ)
    """

    __tablename__ = "user_addresses"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    label: Mapped[str | None] = mapped_column(String(40), nullable=True)  # บ้าน · ที่ทำงาน · คอนโด
    receiver: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    address: Mapped[str] = mapped_column(Text, nullable=False, default="")  # เลขที่ หมู่บ้าน ตึก ถนน ซอย
    sub: Mapped[str | None] = mapped_column(String(120), nullable=True)      # แขวง/ตำบล
    district: Mapped[str | None] = mapped_column(String(120), nullable=True)  # เขต/อำเภอ
    province: Mapped[str | None] = mapped_column(String(120), nullable=True)
    postcode: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)  # จุดสังเกต เช่น ตึกสีเทา ประตูหลัง
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[User] = relationship(back_populates="addresses")

    @property
    def one_line(self) -> str:
        """ที่อยู่บรรทัดเดียวไว้ส่งให้ระบบคิดค่าส่ง/พิมพ์ใบส่งของ"""
        return " ".join(x for x in (self.address, self.sub, self.district, self.province, self.postcode) if x)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    device: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="sessions")


class OtpCode(Base):
    """OTP — ตัวส่งจริงเป็น SMS gateway (ตอนนี้ log ออก console)

    เก็บเป็น hash ไม่เก็บเลขตรงๆ: ใครอ่านฐานได้ (หรือ log/backup หลุด) จะเอา OTP ที่ยังไม่หมดอายุ
    ไปสวมรอยไม่ได้ — หลักเดียวกับที่ refresh token ในตารางข้างบนเก็บเป็น hash
    """

    __tablename__ = "otp_codes"

    id: Mapped[str] = uuid_pk()
    phone: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # login = ยืนยันตัวตนเข้าระบบ · link_member = ยืนยันว่าเป็นเจ้าของเบอร์ที่ผูกกับเลขสมาชิกนั้น
    purpose: Mapped[str] = mapped_column(String(16), default="login", nullable=False)
    # ใช้กับ purpose=link_member — ล็อกไว้ว่ารหัสนี้ใช้ผูกเลขสมาชิกใบไหนได้ใบเดียว
    target: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # กรอกผิดเกินโควตา = รหัสตาย
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class AuthAttempt(Base):
    """บันทึกความพยายามยืนยันตัวตนทุกครั้ง — ใช้นับเพื่อจำกัดอัตราและล็อกชั่วคราว

    แยกจาก audit_logs เพราะตารางนี้ถูกนับถี่มาก (ทุก login/OTP) และลบทิ้งตามอายุได้
    ส่วน audit_logs เก็บไว้ตรวจสอบย้อนหลังระยะยาว
    """

    __tablename__ = "auth_attempts"
    __table_args__ = (Index("ix_auth_attempts_key_created", "key", "created_at"),)

    id: Mapped[str] = uuid_pk()
    # คีย์ที่ใช้นับ เช่น "login:SA-104" · "ip:1.2.3.4" · "otp_send:0949164600"
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # login | otp_send | otp_verify | link_member
    ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class MemberLinkEvent(Base):
    """ประวัติการผูก/ถอด "เลขสมาชิก" เข้ากับบัญชีเว็บ — เขียนอย่างเดียว ไม่แก้ไม่ลบ

    ทำไมต้องแยกจาก audit_logs:
      การผูกเลขสมาชิกคือจุดที่ "บัญชีเว็บ" กับ "ตัวตนจริงในทะเบียนลูกค้า" มาเจอกัน
      ผูกผิดคน = เห็นแต้ม ประวัติการซื้อ ที่อยู่ และเบอร์ของคนอื่นทันที
      เวลามีข้อพิพาทว่า "ใครเอาบัญชีฉันไป" ต้องตอบได้ว่าใครผูกเมื่อไร ด้วยหลักฐานอะไร
      ซึ่งใน audit_logs ปนกับเหตุการณ์อื่นทั้งระบบจนไล่ไม่ไหว

    บันทึกครั้งที่ "ไม่ผ่าน" ด้วย — คนที่ไล่เดาเลขสมาชิกคนอื่นจะทิ้งรอยไว้เป็นชุด
    ของสำเร็จอย่างเดียวมองไม่เห็นความพยายามที่ถูกกันไว้
    """

    __tablename__ = "member_link_events"
    __table_args__ = (Index("ix_member_link_events_cust", "sap_customer_no", "created_at"),)

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    sap_customer_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # linked | unlinked | denied — denied คือพยายามผูกแล้วไม่ผ่าน
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # phone_match = เบอร์ที่ยืนยันแล้วตรงกับทะเบียน · otp = ยืนยัน OTP ที่เบอร์ในทะเบียน
    # staff = พนักงานผูกให้ · ว่าง = ไม่ผ่าน จึงยังไม่มีวิธีพิสูจน์
    via: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # เบอร์ที่ใช้พิสูจน์ ปิดบังไว้ (094-xxx-4600) — เก็บเบอร์เต็มซ้ำไม่มีประโยชน์และเพิ่มของที่ต้องปกป้อง
    phone_masked: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
