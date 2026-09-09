"""ที่อยู่ไทย ตำบล/อำเภอ/จังหวัด + รหัสไปรษณีย์ (thai_geo)

ยกมาจาก directory_subdistrict/district/country_region บน Magento — ดู app/etl/sync_thai_geo.py

Revision ID: d1f4a9c02b77
Revises: c8d21a4f7b30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd1f4a9c02b77'
down_revision: Union[str, None] = 'c8d21a4f7b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'thai_geo',
        sa.Column('subdistrict_id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('zipcode', sa.String(length=5), nullable=False),
        sa.Column('subdistrict_th', sa.String(length=120), nullable=False),
        sa.Column('subdistrict_en', sa.String(length=120), nullable=True),
        sa.Column('district_id', sa.Integer(), nullable=False),
        sa.Column('district_th', sa.String(length=120), nullable=False),
        sa.Column('district_en', sa.String(length=120), nullable=True),
        sa.Column('province_id', sa.Integer(), nullable=False),
        sa.Column('province_th', sa.String(length=120), nullable=False),
        sa.Column('province_en', sa.String(length=120), nullable=True),
        sa.Column('area_id', sa.Integer(), nullable=True),
        sa.Column('is_blocked', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('subdistrict_id'),
    )
    op.create_index(op.f('ix_thai_geo_zipcode'), 'thai_geo', ['zipcode'])
    op.create_index(op.f('ix_thai_geo_district_id'), 'thai_geo', ['district_id'])
    op.create_index(op.f('ix_thai_geo_province_id'), 'thai_geo', ['province_id'])
    op.create_index(op.f('ix_thai_geo_area_id'), 'thai_geo', ['area_id'])


def downgrade() -> None:
    op.drop_table('thai_geo')
