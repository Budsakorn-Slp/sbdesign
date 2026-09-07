from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, auth, cart, catalog, health, sales, ws
from app.core.config import get_settings
from app.realtime import manager, on_cart_event
from app.services import cart_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager.bind_loop()  # ให้ service (sync) ส่ง event เข้า loop ของ websocket ได้
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.5.0", lifespan=lifespan)
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
    app.include_router(ws.router)
    app.include_router(admin.router)
    if on_cart_event not in cart_service._change_hooks:
        cart_service.register_change_hook(on_cart_event)
    return app


app = create_app()
