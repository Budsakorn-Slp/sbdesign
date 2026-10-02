"""materials.shuffle_key — เลขประจำตัวสำหรับสลับลำดับหน้าเว็บ

เดิมหน้าแรกสลับลำดับด้วย CAST(matnr AS BIGINT) แล้วคูณ seed ซึ่งพังบน PostgreSQL
เพราะในฐานมีรหัสที่ไม่ใช่ตัวเลข 491 รหัส (A017, A534, A761 ...) — SQLite แปลงแล้วได้ 0
เงียบๆ แต่ PostgreSQL ตีกลับทั้ง query ด้วย invalid input syntax for type bigint

เก็บเป็นคอลัมน์ int ไว้ตั้งแต่ตอน import จึงพ้นปัญหา และเรียงเร็วกว่าเพราะมี index

Revision ID: a4b81c3f5e92
Revises: 3e7995d9d5f6
Create Date: 2026-10-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4b81c3f5e92"
down_revision: Union[str, None] = "3e7995d9d5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("materials", schema=None) as b:
        b.add_column(sa.Column("shuffle_key", sa.Integer(), nullable=False, server_default="0"))
        b.create_index(b.f("ix_materials_shuffle_key"), ["shuffle_key"], unique=False)

    # เติมค่าให้แถวที่มีอยู่แล้ว — คิดใน Python ด้วยสูตรเดียวกับตอน import
    # (ทำใน SQL ไม่ได้เพราะ crc32 ไม่มีทั้งใน SQLite และ PostgreSQL แบบมาตรฐาน)
    from app.models.catalog import shuffle_key_for

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT matnr FROM materials")).fetchall()
    for i in range(0, len(rows), 1000):
        conn.execute(
            sa.text("UPDATE materials SET shuffle_key = :k WHERE matnr = :m"),
            [{"m": r[0], "k": shuffle_key_for(r[0])} for r in rows[i : i + 1000]],
        )

    # server_default มีไว้ให้ ALTER ผ่านตอนตารางมีข้อมูลอยู่แล้ว ไม่ได้ตั้งใจให้ค้างถาวร
    # ปล่อยไว้แถวใหม่ที่ ETL ลืมใส่ค่าจะได้ 0 ทั้งหมดแล้วไปกองอยู่ที่เดียวกันโดยไม่มีใครรู้
    with op.batch_alter_table("materials", schema=None) as b:
        b.alter_column("shuffle_key", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("materials", schema=None) as b:
        b.drop_index(b.f("ix_materials_shuffle_key"))
        b.drop_column("shuffle_key")
