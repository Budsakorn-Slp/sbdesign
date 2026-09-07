"""seed data - รันซ้ำได้ (idempotent): python -m app.seed"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User

SEED_USERS = [
    # ลูกค้า
    dict(role="customer", name="ณภัทร พงษ์ศรี", phone="0892344471", email="napat@email.com", sap_customer_no="4400182", tier="Gold",
         default_address="88/12 ซ.สุขุมวิท 71 คลองตันเหนือ วัฒนา กทม.", default_postcode="10110"),
    dict(role="customer", name="วีระ ศรีสุข", phone="0812223333", email="weera@email.com", sap_customer_no="4400205", tier="Silver",
         default_address="55 ถ.บางนา-ตราด บางนา กทม.", default_postcode="10260"),
    # พนักงาน
    dict(role="sales", name="สมชาย ก.", staff_code="SA-104", branch_id="BKN", email="somchai@sb.local"),
    dict(role="sales", name="สมหญิง ข.", staff_code="SA-105", branch_id="BKN", email="somying@sb.local"),
    dict(role="manager", name="มานะ ผู้จัดการ", staff_code="MG-001", branch_id="BKN", email="mana@sb.local"),
    dict(role="admin", name="แอดมินระบบ", staff_code="ADM-001", email="admin@sb.local"),
]
DEFAULT_PASSWORD = "1234"


def seed_users(db: Session) -> int:
    n = 0
    for row in SEED_USERS:
        key = User.staff_code == row["staff_code"] if row.get("staff_code") else User.phone == row["phone"]
        if db.scalar(select(User).where(key)):
            continue
        db.add(User(password_hash=hash_password(DEFAULT_PASSWORD), is_guest=False, **row))
        n += 1
    db.commit()
    return n


def run() -> None:
    with SessionLocal() as db:
        print(f"seed users: +{seed_users(db)} (password ทุกบัญชี = {DEFAULT_PASSWORD})")


if __name__ == "__main__":
    run()
