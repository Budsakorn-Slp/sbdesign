import os

os.environ["DATABASE_URL"] = "sqlite:///./test_sbdesign.db"
os.environ["SAP_MODE"] = "mock"
os.environ["OTP_DEBUG"] = "true"
# เครื่อง dev ที่ตั้ง SAP_AVAIL_URL/SAP_API_KEY ไว้ใน .env เทสต้องไม่วิ่งไปยิง SAP ของจริง
os.environ["SAP_AVAIL_URL"] = ""
os.environ["SAP_STOCK_URL"] = ""
os.environ["SAP_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
import app.models  # noqa: E402,F401
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    try:
        os.remove("./test_sbdesign.db")
    except OSError:
        pass


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
