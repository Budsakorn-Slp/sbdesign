"""seed data - รันซ้ำได้ (idempotent): python -m app.seed"""
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.integrations.sap import get_sap_client
from app.models.catalog import Material
from app.models.user import User
from app.services import catalog_service, delivery_service, promo_service, stock_service

SAP_MOCK_DIR = Path(__file__).resolve().parents[1] / "seed" / "sap_mock"

SEED_USERS = [
    # ลูกค้า
    dict(role="customer", name="ณภัทร พงษ์ศรี", phone="0949164600", email="napat@email.com", sap_customer_no="1100440182", points=1250,
         default_address="88/12 ซ.สุขุมวิท 71 คลองตันเหนือ วัฒนา กทม.", default_postcode="10110"),
    dict(role="customer", name="วีระ ศรีสุข", phone="0812223333", email="weera@email.com", sap_customer_no="1100440205", points=340,
         default_address="55 ถ.บางนา-ตราด บางนา กทม.", default_postcode="10260"),
    # พนักงาน
    dict(role="sales", name="สมชาย ก.", staff_code="SA-104", branch_id="BKN", email="somchai@sb.local"),
    dict(role="sales", name="สมหญิง ข.", staff_code="SA-105", branch_id="BKN", email="somying@sb.local"),
    dict(role="manager", name="มานะ ผู้จัดการ", staff_code="MG-001", branch_id="BKN", email="mana@sb.local"),
    dict(role="admin", name="แอดมินระบบ", staff_code="ADM-001", email="admin@sb.local"),
]
DEFAULT_PASSWORD = "1122"


def _load(name: str):
    with open(SAP_MOCK_DIR / name, encoding="utf-8") as f:
        return json.load(f)


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


def seed_catalog(db: Session) -> dict:
    """mirror จาก SAP (mock) -> Group B: categories/brands/plants/materials/prices/stock_cache"""
    catalog_service.upsert_taxonomy(db, _load("categories.json"), _load("brands.json"))
    catalog_service.upsert_plants(db, _load("plants.json"))
    client = get_sap_client()
    added = catalog_service.upsert_materials(db, client.list_materials())
    matnrs = [m for m in db.scalars(select(Material.matnr)).all()]
    cached = stock_service.sync_all_stock_to_cache(db, matnrs)
    promos = promo_service.sync_promotions(db, _load("promotions.json"))
    zones = delivery_service.sync_zones(db, _load("delivery_zones.json"))
    return {"materials_added": added, "materials_total": len(matnrs), "stock_cached": cached, "promotions_added": promos, "zones_added": zones}


def run() -> None:
    with SessionLocal() as db:
        print(f"seed users: +{seed_users(db)} (password ทุกบัญชี = {DEFAULT_PASSWORD})")
        print(f"seed catalog: {seed_catalog(db)}")


if __name__ == "__main__":
    run()
