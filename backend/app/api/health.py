from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    s = get_settings()
    return {"status": "ok", "app": s.app_name, "sap_mode": s.sap_mode, "db": "sqlite" if s.is_sqlite else "postgresql"}
