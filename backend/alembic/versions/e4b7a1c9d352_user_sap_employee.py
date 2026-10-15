"""พนักงาน: ข้อมูลคนขายจาก SAP (auth_source / sap_pernr / sap_sales_office / sap_sales_group / sap_distr_chan)

Revision ID: e4b7a1c9d352
Revises: d8a2f4c6e913
Create Date: 2026-10-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4b7a1c9d352"
down_revision: Union[str, None] = "d8a2f4c6e913"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("auth_source", sa.String(8), nullable=False, server_default="local"))
        b.add_column(sa.Column("sap_pernr", sa.String(10), nullable=True))
        b.add_column(sa.Column("sap_sales_office", sa.String(8), nullable=True))
        b.add_column(sa.Column("sap_sales_group", sa.String(8), nullable=True))
        b.add_column(sa.Column("sap_distr_chan", sa.String(4), nullable=True))
        b.create_index("ix_users_sap_pernr", ["sap_pernr"])


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.drop_index("ix_users_sap_pernr")
        b.drop_column("sap_distr_chan")
        b.drop_column("sap_sales_group")
        b.drop_column("sap_sales_office")
        b.drop_column("sap_pernr")
        b.drop_column("auth_source")
