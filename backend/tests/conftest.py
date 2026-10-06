import os

os.environ["DATABASE_URL"] = "sqlite:///./test_sbdesign.db"
os.environ["SAP_MODE"] = "mock"
os.environ["OTP_DEBUG"] = "true"
# ว่าง = โชว์รหัสได้ทุกเบอร์ · เครื่อง dev ที่ใส่รายชื่อเบอร์ทดสอบไว้ใน .env ต้องไม่มีผลกับเทส
# (ไม่งั้นเทสที่ใช้เบอร์สมมุติจะไม่ได้ debug_code แล้วล้มทั้งแผง)
os.environ["OTP_DEBUG_PHONES"] = ""
# เครื่อง dev ที่ตั้ง SAP_AVAIL_URL/SAP_API_KEY ไว้ใน .env เทสต้องไม่วิ่งไปยิง SAP ของจริง
os.environ["SAP_AVAIL_URL"] = ""
os.environ["SAP_STOCK_URL"] = ""
os.environ["SAP_API_KEY"] = ""
os.environ["SAP_CATALOG_URL"] = ""
# ค่าปกติของระบบคือ "เปิดให้สมัคร" — เทสต้องวัดจากค่านี้เสมอ ไม่ใช่ตามที่เครื่อง dev ตั้งไว้
# (เครื่องที่เปิด INVITE_ONLY=true ไว้ทดลอง จะทำให้เทสล็อกอิน/สมัครล้มทั้งแผง)
# เทสที่ต้องการโหมด invite_only เปิดเองเฉพาะกรณี ดู fixture invite_only
os.environ["INVITE_ONLY"] = "false"
# เทสวิ่งบน http (TestClient) — APP_ENV=prod จะทำให้คุกกี้ตะกร้าติดธง Secure
# ซึ่งใช้ได้เฉพาะ https คุกกี้จึงไม่ถูกเก็บ แล้วเทสของ guest/websocket จะค้างรอตลอดไป
# เครื่องที่ตั้ง prod ไว้เพื่อ deploy ต้องไม่ลากเทสไปด้วย
os.environ["APP_ENV"] = "dev"
# ธุรกิจรับชำระเต็มจำนวนอย่างเดียว — เทสต้องวัดจากค่านี้ ไม่ใช่ตามที่เครื่อง dev ตั้งไว้
# เทสที่ต้องการทดสอบทางมัดจำเปิดเองเฉพาะกรณี ดู fixture deposit_on ใน test_step9_payment
os.environ["DEPOSIT_ENABLED"] = "false"
# ส่วนลดพนักงานปิดแล้วเช่นกัน — เทสที่ยังทดสอบกลไกนี้เปิดเองผ่าน fixture staff_discount_on
os.environ["STAFF_DISCOUNT_ENABLED"] = "false"
# เครื่องที่เปิดปุ่มจ่ายเงินจำลองไว้ให้ทีมลองบนเว็บทดสอบ ต้องไม่ลากเทสไปด้วย
# เทสเรื่องด่าน prod ต้องวัดจากค่าตั้งต้นของระบบ (ปิด) ไม่ใช่ค่าที่เครื่องนี้ตั้งไว้
os.environ["MOCK_PAYMENT_ENABLED"] = "false"

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
