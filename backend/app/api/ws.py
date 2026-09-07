from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.user import User
from app.realtime import manager
from app.services import cart_service

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/cart/{cart_id}")
async def cart_ws(ws: WebSocket, cart_id: str, token: str | None = Query(default=None), anon: str | None = Query(default=None)):
    """เหตุการณ์ item_added / item_updated / item_removed / item_acked / cart_merged / customer_attached / customer_detached / session_closed
    auth: ?token=<access_token> (ลูกค้า/เซลล์) หรือ ?anon=<sb_anon cookie> (guest) — สิทธิ์เดียวกับ REST
    """
    user: User | None = None
    with SessionLocal() as db:
        if token:
            payload = decode_access_token(token)
            if payload:
                user = db.get(User, payload["sub"])
        anon_token = anon or ws.cookies.get(cart_service.ANON_COOKIE)
        cart = cart_service.load_cart(db, cart_id)
        if not cart or not cart_service.can_access(cart, user, anon_token):
            await ws.close(code=1008, reason="ไม่มีสิทธิ์เข้าถึงตะกร้านี้")
            return
        role = user.role if user else "guest"
    await manager.connect(cart_id, ws)
    try:
        await ws.send_json({"type": "hello", "cart_id": cart_id, "role": role, "connections": manager.connections(cart_id)})
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(cart_id, ws)
        if ws.client_state == WebSocketState.CONNECTED:
            try:
                await ws.close()
            except Exception:
                pass
