"""รูปตัวโชว์: แชร์ให้ลูกค้าเห็น (อัปโหลดแล้วเห็นเฉพาะพนักงานจนกว่าจะกดแชร์)

Revision ID: a7c3e9f15d22
Revises: f2a6c8d14b90
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e9f15d22"
down_revision: Union[str, None] = "f2a6c8d14b90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("product_photos") as b:
        b.add_column(sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("shared_by_employee", sa.String(32), nullable=True))
        b.add_column(sa.Column("shared_at", sa.DateTime(), nullable=True))
    op.create_index("ix_product_photos_public", "product_photos", ["matnr", "is_public", "is_deleted"])


def downgrade() -> None:
    op.drop_index("ix_product_photos_public", table_name="product_photos")
    with op.batch_alter_table("product_photos") as b:
        b.drop_column("shared_at")
        b.drop_column("shared_by_employee")
        b.drop_column("is_public")
