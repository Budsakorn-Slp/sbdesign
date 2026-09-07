import { useEffect, useRef } from "react";
import { API_BASE, loadAuth } from "./api";

export type CartEvent = {
  type: "hello" | "item_added" | "item_updated" | "item_removed" | "item_acked" | "cart_merged" | "customer_attached" | "customer_detached" | "session_closed";
  cart_id: string;
  cart_no?: string;
  at?: string;
  item_id?: string;
  matnr?: string;
  qty?: number;
  added_by?: "customer" | "sales";
  by_name?: string | null;
  customer_name?: string;
  sales_name?: string;
  moved?: number;
  outcome?: string;
  role?: string;
};

function anonCookie(): string | null {
  const m = document.cookie.match(/(?:^|;\s*)sb_anon=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

function wsUrl(cartId: string): string {
  const auth = loadAuth();
  const qs = new URLSearchParams();
  if (auth) qs.set("token", auth.access_token);
  else {
    const a = anonCookie();
    if (a) qs.set("anon", a);
  }
  // API_BASE = "/api" (proxy) → websocket ผ่าน /ws ที่ vite proxy ไป api เช่นกัน · ถ้า API_BASE เป็น URL เต็มให้แปลง scheme
  const base = API_BASE.startsWith("http") ? API_BASE.replace(/^http/, "ws").replace(/\/api$/, "") : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}`;
  return `${base}/ws/cart/${cartId}?${qs.toString()}`;
}

/** subscribe เหตุการณ์ของตะกร้า — reconnect อัตโนมัติ, ส่ง ping ทุก 25 วิ */
export function useCartSocket(cartId: string | null | undefined, onEvent: (evt: CartEvent) => void): void {
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    if (!cartId) return;
    let ws: WebSocket | null = null;
    let closed = false;
    let retry = 0;
    let timer: number | undefined;
    let ping: number | undefined;

    const open = () => {
      if (closed) return;
      try {
        ws = new WebSocket(wsUrl(cartId));
      } catch {
        return;
      }
      ws.onopen = () => {
        retry = 0;
        ping = window.setInterval(() => ws && ws.readyState === WebSocket.OPEN && ws.send("ping"), 25000);
      };
      ws.onmessage = (m) => {
        if (typeof m.data !== "string" || m.data === "pong") return;
        try {
          handler.current(JSON.parse(m.data) as CartEvent);
        } catch {
          /* ignore */
        }
      };
      ws.onclose = (e) => {
        if (ping) window.clearInterval(ping);
        if (closed || e.code === 1008) return; // 1008 = ไม่มีสิทธิ์ ไม่ต้อง reconnect
        retry += 1;
        timer = window.setTimeout(open, Math.min(15000, 1000 * 2 ** retry));
      };
      ws.onerror = () => ws && ws.close();
    };
    open();
    return () => {
      closed = true;
      if (timer) window.clearTimeout(timer);
      if (ping) window.clearInterval(ping);
      if (ws) ws.close();
    };
  }, [cartId]);
}
