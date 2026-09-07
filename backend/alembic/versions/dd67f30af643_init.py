"""init

Revision ID: dd67f30af643
Revises: 
Create Date: 2026-09-07 15:11:27.682157
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'dd67f30af643'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
