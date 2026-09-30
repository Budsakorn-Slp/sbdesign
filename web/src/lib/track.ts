import { apiPost } from "./api";

/** ส่ง event พฤติกรรมผู้ใช้ไปเก็บที่ฐานข้อมูล (ตาราง user_events)
 *
 * กฎของที่นี่: **ห้ามทำให้หน้าเว็บพังหรือช้าเพราะการเก็บสถิติ** — ยิงแบบไม่รอผล
 * และกลืน error ทิ้งทั้งหมด ถ้าเก็บไม่ได้ก็แค่ไม่มีข้อมูลแถวนั้น ผู้ใช้ต้องไม่รู้สึกอะไรเลย
 *
 * ตัวตนผูกให้เองที่ฝั่ง backend — ล็อกอินอยู่ใช้ user_id · ยังไม่ล็อกอินใช้คุกกี้ sb_anon
 * (อายุ 90 วัน) ลูกค้าคนเดิมล็อกอินกลับมาเมื่อไหร่ ข้อมูลก็ยังผูกกับบัญชีเดิม
 */
type Event = "page_view" | "click_product" | "search" | "view_material";

function send(event: Event, body: Record<string, unknown> = {}): void {
  void apiPost("/events", { event, ...body }).catch(() => {});
}

/** เปิดหน้าไหน — เรียกทุกครั้งที่เปลี่ยน route (ดู Layout) */
export function trackPageView(path: string): void {
  send("page_view", { path });
}

/** กดการ์ดสินค้า · from บอกว่ากดมาจากไหน (search → ผูกกลับไปที่คำค้นนั้นด้วย) */
export function trackProductClick(matnr: string, from: "search" | "home" | "related" | "cart" | "other", q?: string): void {
  send("click_product", { matnr, path: location.pathname, payload: { from, ...(q ? { q } : {}) } });
}
