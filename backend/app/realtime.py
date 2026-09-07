"""Realtime: WebSocket ต่อตะกร้า (FastAPI native)
- เซลล์เพิ่มของ → มือถือลูกค้าเด้งการ์ดทันที (item_added)
- ทุก mutation ใน cart_service.emit(...) จะถูก broadcast มาที่ห้องของ cart_id นั้น
- โค้ด service เป็น sync (รันใน threadpool) จึงส่งเข้า event loop ด้วย run_coroutine_threadsafe
"""
import asyncio
import json
import logging
from collections import defaultdict

from fastapi import WebSocket

from app.models.cart import Cart
from app.models.common import utcnow

log = logging.getLogger("sb.realtime")


class ConnectionManager:
    def __init__(self) -> None:
        self.rooms: dict[str, set[WebSocket]] = defaultdict(set)
        self.loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self) -> None:
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = None

    async def connect(self, cart_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self.rooms[cart_id].add(ws)

    def disconnect(self, cart_id: str, ws: WebSocket) -> None:
        self.rooms[cart_id].discard(ws)
        if not self.rooms[cart_id]:
            self.rooms.pop(cart_id, None)

    async def broadcast(self, cart_id: str, message: dict) -> None:
        dead: list[WebSocket] = []
        text = json.dumps(message, ensure_ascii=False, default=str)
        for ws in list(self.rooms.get(cart_id, ())):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(cart_id, ws)

    def broadcast_threadsafe(self, cart_id: str, message: dict) -> None:
        if not self.loop or self.loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            self.loop.create_task(self.broadcast(cart_id, message))
        else:
            asyncio.run_coroutine_threadsafe(self.broadcast(cart_id, message), self.loop)

    def connections(self, cart_id: str) -> int:
        return len(self.rooms.get(cart_id, ()))


manager = ConnectionManager()


def on_cart_event(cart: Cart, event: str, payload: dict) -> None:
    """hook จาก cart_service.emit"""
    msg = {"type": event, "cart_id": cart.id, "cart_no": cart.no, "at": utcnow().isoformat(), **payload}
    manager.broadcast_threadsafe(cart.id, msg)
