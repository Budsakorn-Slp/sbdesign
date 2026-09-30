"""info_pages — หน้าเนื้อหาคงที่ที่ยกมาจาก CMS ของเว็บจริง

Revision ID: c5e2a83f14d6
Revises: b2d4f60a9c17
Create Date: 2026-09-16 11:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5e2a83f14d6'
down_revision: Union[str, None] = 'b2d4f60a9c17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'info_pages',
        sa.Column('slug', sa.String(length=80), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=False),
        sa.Column('source_url', sa.String(length=300), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('slug'),
    )


def downgrade() -> None:
    op.drop_table('info_pages')
