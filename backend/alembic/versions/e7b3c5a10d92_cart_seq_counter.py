"""เลขตะกร้าจริง: doc_counters + carts.seq แล้วไล่เลขใหม่เป็น 001, 002, ...

ของเดิมเลขมาจาก 8823 + COUNT(*) ซึ่งเลื่อนได้เมื่อมีการลบแถวและชนกันได้เมื่อเปิดพร้อมกัน
รอบนี้จะเริ่มเก็บข้อมูลจริง เลยไล่เลขใหม่ทั้งหมดตามลำดับเวลาที่เปิดตะกร้า
(ตะกร้าเก่าเป็นข้อมูลทดลอง — เลขใน snapshot ใบเสนอราคาเก่าจะไม่ตรงกับเลขใหม่)

Revision ID: e7b3c5a10d92
Revises: d1f4a9c02b77
"""
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e7b3c5a10d92'
down_revision: Union[str, None] = 'd1f4a9c02b77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'doc_counters',
        sa.Column('key', sa.String(length=32), nullable=False),
        sa.Column('next_value', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    with op.batch_alter_table('carts') as b:  # SQLite เพิ่มคอลัมน์ที่มี UNIQUE ตรง ๆ ไม่ได้
        b.add_column(sa.Column('seq', sa.Integer(), nullable=True))
        b.create_unique_constraint('uq_carts_seq', ['seq'])

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id FROM carts ORDER BY created_at, id")).fetchall()
    for n, (cart_id,) in enumerate(rows, start=1):
        conn.execute(sa.text("UPDATE carts SET seq = :n, no = :no WHERE id = :id"),
                     {"n": n, "no": f"{n:03d}", "id": cart_id})
    conn.execute(sa.text("INSERT INTO doc_counters (key, next_value, updated_at) VALUES ('cart', :n, :ts)"),
                 {"n": len(rows) + 1, "ts": datetime.now(timezone.utc).replace(tzinfo=None)})


def downgrade() -> None:
    with op.batch_alter_table('carts') as b:
        b.drop_constraint('uq_carts_seq', type_='unique')
        b.drop_column('seq')
    op.drop_table('doc_counters')
