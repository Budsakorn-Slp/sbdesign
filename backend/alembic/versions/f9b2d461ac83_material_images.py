"""material_images — แกลเลอรีรูปสินค้าหลายใบต่อรหัส

Revision ID: f9b2d461ac83
Revises: e3a7c05d9b12
Create Date: 2026-09-16 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f9b2d461ac83'
down_revision: Union[str, None] = 'e3a7c05d9b12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'material_images',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('matnr', sa.String(length=18), nullable=False),
        sa.Column('url', sa.String(length=400), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('label', sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(['matnr'], ['materials.matnr'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('matnr', 'url', name='uq_material_image'),
    )
    op.create_index('ix_material_images_matnr', 'material_images', ['matnr'])


def downgrade() -> None:
    op.drop_index('ix_material_images_matnr', table_name='material_images')
    op.drop_table('material_images')
