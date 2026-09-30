import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, analytics, auth, cart, catalog, delivery, geo, health, payment, pdpa, promo, quotation, sales, ws
from app.core.config import get_settings
from app.realtime import manager, on_cart_event
from app.services import cart_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager.bind_loop()  # ให้ service (sync) ส่ง event เข้า loop ของ websocket ได้
    yield


def _setup_logging(level: str) -> None:
    """ให้ log ของโค้ดเราโผล่ใน console จริงๆ

    uvicorn ตั้งค่าเฉพาะ logger ของตัวเอง — logger ของแอป (sb.*) จึงตกไปอยู่กับ root
    ที่ไม่มี handler และ Python จะแสดงเฉพาะ WARNING ขึ้นไปเท่านั้น ผลคือบรรทัดอย่าง
    [MOCK SMS] ที่พิมพ์รหัส OTP หายไปเงียบๆ ทั้งที่โค้ดเรียก log.info ไว้แล้ว
    """
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # httpx log ทุก request ที่ยิงออกไป — มีประโยชน์ตอนดีบัก แต่รกเกินไปในการใช้งานปกติ
    logging.getLogger("httpx").setLevel(logging.WARNING)


def create_app() -> FastAPI:
    settings = get_settings()
    _setup_logging(settings.log_level)
    app = FastAPI(title=settings.app_name, version="0.11.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(catalog.router)
    app.include_router(cart.router)
    app.include_router(sales.router)
    app.include_router(promo.router)
    app.include_router(delivery.router)
    app.include_router(geo.router)
    app.include_router(quotation.router)
    app.include_router(payment.router)
    app.include_router(analytics.router)
    app.include_router(pdpa.router)
    app.include_router(ws.router)
    app.include_router(admin.router)
    if on_cart_event not in cart_service._change_hooks:
        cart_service.register_change_hook(on_cart_event)
    return app


app = create_app()
