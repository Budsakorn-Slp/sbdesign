"""ความปลอดภัยการล็อกอิน + ผูกเลขสมาชิก

- users.phone_verified_at : เบอร์ผ่าน OTP แล้วหรือยัง (เงื่อนไขตั้งต้นของการผูกเลขสมาชิก)
- otp_codes               : เก็บ hash แทนเลขตรงๆ + purpose/target/attempts
- auth_attempts           : ตัวนับสำหรับจำกัดอัตราและล็อกชั่วคราว

OTP ใบเก่าถูกทิ้งทั้งหมดตอน migrate — อายุแค่ 5 นาที และแปลงเป็น hash ย้อนหลังไม่ได้
(ถ้ามีคนค้างอยู่กลางทางพอดี แค่กดขอรหัสใหม่)

Revision ID: c7d31e58ab40
Revises: b4e2f1a7c308
"""
import sqlalchemy as sa
from alembic import op

revision = "c7d31e58ab40"
down_revision = "b4e2f1a7c308"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone_verified_at", sa.DateTime(), nullable=True))

    op.execute(sa.text("DELETE FROM otp_codes"))
    with op.batch_alter_table("otp_codes") as b:
        b.add_column(sa.Column("code_hash", sa.String(64), nullable=False, server_default=""))
        b.add_column(sa.Column("purpose", sa.String(16), nullable=False, server_default="login"))
        b.add_column(sa.Column("target", sa.String(64), nullable=True))
        b.add_column(sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
        b.drop_column("code")

    op.create_table(
        "auth_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_auth_attempts_key_created", "auth_attempts", ["key", "created_at"])
    op.create_index("ix_auth_attempts_created_at", "auth_attempts", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_attempts_created_at", table_name="auth_attempts")
    op.drop_index("ix_auth_attempts_key_created", table_name="auth_attempts")
    op.drop_table("auth_attempts")

    op.execute(sa.text("DELETE FROM otp_codes"))
    with op.batch_alter_table("otp_codes") as b:
        b.add_column(sa.Column("code", sa.String(8), nullable=False, server_default=""))
        b.drop_column("attempts")
        b.drop_column("target")
        b.drop_column("purpose")
        b.drop_column("code_hash")

    op.drop_column("users", "phone_verified_at")
