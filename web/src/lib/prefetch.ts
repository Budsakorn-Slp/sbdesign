import { useEffect } from "react";
import type { Role } from "./types";

/** โหลดโค้ดของหน้าที่ "รู้อยู่แล้วว่าคนนี้ต้องใช้" ไว้ล่วงหน้าตอนเบราว์เซอร์ว่าง
 *
 * หน้าแต่ละหน้าถูกแยกเป็นไฟล์ของตัวเอง (ดู App.tsx) ปกติจึงเริ่มโหลดตอนกดเข้าไปแล้ว
 * ซึ่งช้าไปหนึ่งจังหวะ — เห็นโครงเปล่าแวบหนึ่งทุกครั้งที่เข้าหน้าใหม่ครั้งแรกของวัน
 *
 * แทนที่จะเดาจากการเอาเมาส์ชี้ (prefetch on hover) เราใช้สิ่งที่รู้แน่นอนกว่า: เซลล์เปิด
 * มาก็ต้องเข้าหน้าตะกร้า/ใบเสนอราคาอยู่แล้ว ไม่มีทางไม่เข้า — โหลดรอไว้เลยตั้งแต่ตอนว่าง
 * ลูกค้าทั่วไปไม่โดนผลกระทบ เพราะไม่มีรายการของ role "customer"
 */
type Loader = () => Promise<unknown>;

// ต้องเขียน path ให้ตรงกับใน App.tsx เป๊ะๆ — Vite ถึงจะรู้ว่าเป็นไฟล์ก้อนเดียวกัน
// ถ้าเขียนต่างกัน (เช่น ใส่ .tsx ต่อท้าย) จะกลายเป็นคนละ chunk แล้วโหลดซ้ำฟรีๆ
const SALES: Loader[] = [
  () => import("../pages/SalesPage"),
  () => import("../pages/PresosPage"),
  () => import("../pages/QuotationPage"),
];
const MANAGER: Loader[] = [...SALES, () => import("../pages/ApprovalsPage"), () => import("../pages/SapSyncPage")];

const BY_ROLE: Partial<Record<Role, Loader[]>> = {
  sales: SALES,
  manager: MANAGER,
  admin: MANAGER,
};

/** เน็ตมือถือแบบจ่ายตามปริมาณ / สัญญาณแย่ — อย่าไปดึงของที่ยังไม่ได้ขอ */
function shouldSkip(): boolean {
  const c = (navigator as { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
  if (!c) return false;
  return !!c.saveData || c.effectiveType === "slow-2g" || c.effectiveType === "2g";
}

export function usePrefetchForRole(role: Role): void {
  useEffect(() => {
    const loaders = BY_ROLE[role];
    if (!loaders || shouldSkip()) return;
    // รอจนเบราว์เซอร์ว่างจริงๆ ไม่ไปแย่งแบนด์วิดท์กับรูปสินค้า/ข้อมูลของหน้าที่กำลังเปิดอยู่
    // Safari ยังไม่มี requestIdleCallback — ถอยไปใช้ setTimeout หน่วงยาวๆ แทน
    const idle = window.requestIdleCallback ?? ((cb: () => void) => window.setTimeout(cb, 2000));
    const cancel = window.cancelIdleCallback ?? window.clearTimeout;
    // import ซ้ำไม่เสียอะไร เบราว์เซอร์แคชโมดูลให้อยู่แล้ว · พังก็ปล่อยเงียบ เดี๋ยวตอนกดเข้าไปจริงค่อยโหลดใหม่
    const id = idle(() => loaders.forEach((load) => void load().catch(() => {})));
    return () => cancel(id as number);
  }, [role]);
}
