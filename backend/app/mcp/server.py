"""MCP server (stdio) ของ SB Sales App — ต่อ Claude เข้ามาค้นสินค้าและออกใบเสนอราคา

สั่งจากโฟลเดอร์ backend:

    .venv\\Scripts\\python.exe -m app.mcp.server

ตั้งค่าผ่าน environment variable (ดู docs/mcp.md):
    SB_API_BASE           ที่อยู่ backend (ค่าเริ่มต้น http://localhost:8000)
    SB_MCP_STAFF_CODE     รหัสพนักงานที่ให้ MCP ใช้
    SB_MCP_STAFF_PASSWORD รหัสผ่านของบัญชีนั้น
    SB_MCP_ALLOW_WRITE    ตั้งเป็น 0 เพื่อเปิดเฉพาะเครื่องมืออ่านอย่างเดียว (ค่าเริ่มต้น = เปิดเขียน)

ทำไมเขียนโปรโตคอลเอง ไม่ลง SDK: เครื่องนี้ลงแพ็กเกจเพิ่มไม่สะดวก และที่ MCP ต้องการจริงๆ
คือ JSON-RPC ผ่าน stdin/stdout สามเมท็อด (initialize / tools/list / tools/call) เท่านั้น
พึ่ง httpx ที่โปรเจกต์มีอยู่แล้วตัวเดียว จะได้รันด้วย venv เดิมโดยไม่ต้องติดตั้งอะไรเพิ่ม
"""
import json
import logging
import os
import sys
from typing import Any

from app.mcp.api import Api, ApiError
from app.mcp.tools import by_name, specs

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "sbdesign", "title": "SB Design Square", "version": "1.0.0"}

# เครื่องมือที่แก้ข้อมูลจริง — ปิดได้ด้วย SB_MCP_ALLOW_WRITE=0 ถ้าอยากให้ Claude ดูอย่างเดียว
WRITE_TOOLS = {"open_cart", "add_item", "remove_item", "attach_customer", "quote_delivery", "pick_slot", "create_quotation", "cancel_quotation"}

log = logging.getLogger("sb.mcp")


def _allowed() -> list[dict]:
    if os.environ.get("SB_MCP_ALLOW_WRITE", "1") not in ("0", "false", "no"):
        return specs()
    return [t for t in specs() if t["name"] not in WRITE_TOOLS]


def _text(payload: Any) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2, default=str)}]}


def _error(msg: str) -> dict:
    # ส่งกลับเป็นผลลัพธ์ที่ isError ไม่ใช่ error ของ JSON-RPC — Claude จะได้อ่านข้อความแล้วแก้เอง
    return {"content": [{"type": "text", "text": msg}], "isError": True}


class Server:
    def __init__(self) -> None:
        self.api = Api()
        self.tools = by_name()

    def handle(self, req: dict) -> dict | None:
        method = req.get("method")
        rid = req.get("id")
        if rid is None:  # notification — ไม่ต้องตอบ
            return None
        try:
            result = self.dispatch(method, req.get("params") or {})
        except ApiError as e:
            return {"jsonrpc": "2.0", "id": rid, "result": _error(str(e))}
        except KeyError:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"ไม่รู้จักเมท็อด {method}"}}
        except Exception as e:  # noqa: BLE001 — ล้มทั้ง server เพราะ tool เดียวไม่คุ้ม
            log.exception("tool error")
            return {"jsonrpc": "2.0", "id": rid, "result": _error(f"{type(e).__name__}: {e}")}
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    def dispatch(self, method: str, params: dict) -> Any:
        if method == "initialize":
            return {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {"listChanged": False}}, "serverInfo": SERVER_INFO}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": _allowed()}
        if method == "tools/call":
            return self.call(params.get("name") or "", params.get("arguments") or {})
        raise KeyError(method)

    def call(self, name: str, args: dict) -> Any:
        spec = self.tools.get(name)
        if not spec or name not in {t["name"] for t in _allowed()}:
            return _error(f"ไม่มีเครื่องมือชื่อ {name}")
        missing = [k for k in spec["inputSchema"]["required"] if args.get(k) in (None, "")]
        if missing:
            return _error(f"ขาดค่าที่ต้องส่ง: {', '.join(missing)}")
        return _text(spec["handler"](self.api, args))


def main() -> int:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)  # stdout สงวนให้โปรโตคอลเท่านั้น
    sys.stdin.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    server = Server()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        for one in req if isinstance(req, list) else [req]:
            res = server.handle(one)
            if res is not None:
                sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
                sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
