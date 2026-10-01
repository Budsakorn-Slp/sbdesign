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
    # บน prod ปิดหน้าเอกสาร API — /docs กับ /openapi.json บอกทุก endpoint ทุกพารามิเตอร์
    # เท่ากับแจกแผนที่ระบบให้คนที่กำลังหาช่องโหว่ · บนเครื่อง dev ยังเปิดไว้ตามเดิม
    docs = {} if not settings.is_prod else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title=settings.app_name, version="0.11.0", lifespan=lifespan, **docs)

    @app.middleware("http")
    async def security_headers(request, call_next):
        """หัวข้อความปลอดภัยพื้นฐาน — กันคลิกแจ็ก กันเดาชนิดไฟล์ กันข้อมูลรั่วทาง referrer

        ใส่ที่ชั้นแอปไม่ใช่ที่ Cloudflare อย่างเดียว เพราะวันหนึ่งอาจมีคนต่อตรงเข้าเครื่อง
        (เช่น ทดสอบในวง LAN) แล้วหัวพวกนี้ต้องยังอยู่
        """
        r = await call_next(request)
        r.headers.setdefault("X-Content-Type-Options", "nosniff")
        r.headers.setdefault("X-Frame-Options", "DENY")
        r.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        r.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if settings.is_prod:
            # บอกเบราว์เซอร์ว่าโดเมนนี้ใช้ HTTPS เท่านั้น — ใส่เฉพาะ prod
            # ถ้าใส่ตอน dev เบราว์เซอร์จะจำแล้วบังคับ https กับ localhost ไปด้วย เปิดเว็บไม่ได้
            r.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return r

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
