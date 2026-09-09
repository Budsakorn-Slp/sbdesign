"""ตารางค่าส่งของเราเอง (ship_areas / ship_area_postcodes / ship_rates / ship_rules / ship_product_attrs)

ยกมาจาก Amasty Shipping Rules บน Magento แล้วคลีน — ดู app/etl/sync_shipping_rules.py

Revision ID: c8d21a4f7b30
Revises: a5c81f2ed310
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c8d21a4f7b30'
down_revision: Union[str, None] = 'a5c81f2ed310'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ship_areas',
        sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('code', sa.String(length=16), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('is_default', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_table(
        'ship_area_postcodes',
        sa.Column('prefix', sa.String(length=5), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(['area_id'], ['ship_areas.id']),
        sa.PrimaryKeyConstraint('prefix'),
    )
    op.create_index(op.f('ix_ship_area_postcodes_area_id'), 'ship_area_postcodes', ['area_id'])
    op.create_table(
        'ship_rates',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=False),
        sa.Column('weight_from', sa.Numeric(10, 3), nullable=False),
        sa.Column('weight_to', sa.Numeric(10, 3), nullable=False),
        sa.Column('fee', sa.Numeric(12, 2), nullable=False),
        sa.Column('source_rule_id', sa.Integer(), nullable=True),
        sa.Column('note', sa.String(length=200), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['area_id'], ['ship_areas.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('area_id', 'weight_from', name='uq_ship_rate_area_from'),
    )
    op.create_index(op.f('ix_ship_rates_area_id'), 'ship_rates', ['area_id'])
    op.create_table(
        'ship_rules',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('code', sa.String(length=40), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('priority', sa.Integer(), server_default='0', nullable=False),
        sa.Column('stop_on_match', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('fee', sa.Numeric(12, 2), server_default='0', nullable=False),
        sa.Column('conditions', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('source_rule_id', sa.Integer(), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_index(op.f('ix_ship_rules_priority'), 'ship_rules', ['priority'])
    op.create_index(op.f('ix_ship_rules_is_active'), 'ship_rules', ['is_active'])
    op.create_table(
        'ship_product_attrs',
        sa.Column('sku', sa.String(length=40), nullable=False),
        sa.Column('weight_kg', sa.Numeric(10, 3), nullable=True),
        sa.Column('flat_pack', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('flatpack_not_seller', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('flat_pack_bulky', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('attr_19_rule', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('attr_25_rule', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('sku'),
    )
    op.create_index(op.f('ix_ship_product_attrs_flatpack_not_seller'), 'ship_product_attrs', ['flatpack_not_seller'])


def downgrade() -> None:
    op.drop_table('ship_product_attrs')
    op.drop_table('ship_rules')
    op.drop_table('ship_rates')
    op.drop_table('ship_area_postcodes')
    op.drop_table('ship_areas')
