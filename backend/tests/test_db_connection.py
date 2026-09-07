"""test การเชื่อมต่อ DB

- test_engine_connects: DB ที่ test ใช้ (sqlite) ต้องต่อได้เสมอ
- test_external_db_connects: ถ้าตั้ง env DBCHECK_URL จะลองต่อ DB จริง (เช่น Postgres ใน docker) — ไม่ตั้งจะ skip

    DBCHECK_URL=postgresql+psycopg://sb:sb_secret@localhost:5432/sbdesign pytest tests/test_db_connection.py -s
"""
import os

import pytest
from sqlalchemy import text

from app.db.session import engine
from app.dbcheck import check


def test_engine_connects():
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1


@pytest.mark.skipif(not os.environ.get("DBCHECK_URL"), reason="ตั้ง DBCHECK_URL เพื่อทดสอบต่อ DB จริง")
def test_external_db_connects():
    url = os.environ["DBCHECK_URL"]
    assert check(url), f"ต่อ DB ไม่ได้: {url}"
