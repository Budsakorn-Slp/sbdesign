"""งานหน้าพนักงานขาย: รูปตัวโชว์รายสาขา · หมายเหตุตะกร้า · พนักงานร่วมบิล · template ใบเสนอราคา

  product_photos         รูปที่พนักงานถ่ายของจริงในสาขาตัวเอง (soft delete)
  product_photo_audit    ประวัติ CREATE/UPDATE/DELETE — ไม่มี FK ไปที่รูป ลบรูปแล้วประวัติไม่หาย
  cart_staff             พนักงาน Z1/Z2/Z3/Z4/ZK ของบิล
  quotation_templates    template ส่วนตัวของ DS แต่ละคน
  carts.overall_remark            หมายเหตุหลัก (คนละช่องกับ cart_items.note = หมายเหตุรายสินค้า)
  quotation_lines.item_remark     หมายเหตุรายสินค้าที่ติดไปกับใบ
  quotations.overall_remark / staff_snapshot / template_snapshot   ค่า ณ ตอนออกใบ

Revision ID: f2a6c8d14b90
Revises: e5b73c1d80a4
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2a6c8d14b90"
down_revision: Union[str, None] = "e5b73c1d80a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_photos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("matnr", sa.String(18), nullable=False),
        sa.Column("branch_code", sa.String(16), nullable=False),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owner_employee_code", sa.String(32), nullable=False),
        sa.Column("owner_employee_name", sa.String(120), nullable=False),
        sa.Column("file_path", sa.String(300), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_employee", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by_employee", sa.String(32), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_by_employee", sa.String(32), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_product_photos_matnr_branch", "product_photos", ["matnr", "branch_code", "is_deleted"])
    op.create_index("ix_product_photos_branch_code", "product_photos", ["branch_code"])
    op.create_index("ix_product_photos_owner_user_id", "product_photos", ["owner_user_id"])

    op.create_table(
        "product_photo_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("image_id", sa.String(36), nullable=False),
        sa.Column("matnr", sa.String(18), nullable=False),
        sa.Column("branch_code", sa.String(16), nullable=False),
        sa.Column("image_owner_employee", sa.String(32), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("action_by_employee", sa.String(32), nullable=False),
        sa.Column("action_by_role", sa.String(16), nullable=False),
        sa.Column("action_at", sa.DateTime(), nullable=False),
        sa.Column("old_image_path", sa.String(300), nullable=True),
        sa.Column("new_image_path", sa.String(300), nullable=True),
    )
    op.create_index("ix_product_photo_audit_image_id", "product_photo_audit", ["image_id"])
    op.create_index("ix_product_photo_audit_matnr", "product_photo_audit", ["matnr"])
    op.create_index("ix_product_photo_audit_action_at", "product_photo_audit", ["action_at"])

    op.create_table(
        "cart_staff",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("cart_id", sa.String(36), sa.ForeignKey("carts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_code", sa.String(4), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("employee_code", sa.String(32), nullable=False),
        sa.Column("employee_name", sa.String(120), nullable=False),
        sa.Column("assigned_by", sa.String(32), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_cart_staff_cart_id", "cart_staff", ["cart_id"])
    # บทบาทละหนึ่งคนต่อบิล — กันที่ฐานด้วย ไม่ใช่เชื่อโค้ดอย่างเดียว
    op.create_index("ux_cart_staff_cart_role", "cart_staff", ["cart_id", "role_code"], unique=True)

    op.create_table(
        "quotation_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("employee_code", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("logo_path", sa.String(300), nullable=True),
        sa.Column("bank_accounts", sa.Text(), nullable=True),
        sa.Column("footer_terms", sa.Text(), nullable=True),
        sa.Column("standard_remark", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    with op.batch_alter_table("carts") as b:
        b.add_column(sa.Column("overall_remark", sa.Text(), nullable=True))
    with op.batch_alter_table("quotation_lines") as b:
        b.add_column(sa.Column("item_remark", sa.Text(), nullable=True))
    with op.batch_alter_table("quotations") as b:
        b.add_column(sa.Column("overall_remark", sa.Text(), nullable=True))
        b.add_column(sa.Column("staff_snapshot", sa.JSON(), nullable=True))
        b.add_column(sa.Column("template_snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("quotations") as b:
        b.drop_column("template_snapshot")
        b.drop_column("staff_snapshot")
        b.drop_column("overall_remark")
    with op.batch_alter_table("quotation_lines") as b:
        b.drop_column("item_remark")
    with op.batch_alter_table("carts") as b:
        b.drop_column("overall_remark")
    op.drop_table("quotation_templates")
    op.drop_index("ux_cart_staff_cart_role", table_name="cart_staff")
    op.drop_table("cart_staff")
    op.drop_table("product_photo_audit")
    op.drop_table("product_photos")
