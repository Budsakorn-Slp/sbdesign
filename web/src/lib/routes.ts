import type { Role } from "./types";

/** หน้าไหนต้องมีสิทธิ์อะไร และถ้าไม่มีให้พาไปไหน — ตารางเดียวใช้ทั้งแอป
 *
 * มีไว้แก้อาการ "ค้างอยู่หน้าที่เข้าไม่ได้แล้ว": พอออกจากระบบ (หรือ session หมดอายุเอง)
 * ทั้งที่ยังเปิดหน้าตะกร้าเซลล์/หน้าบัญชีอยู่ ของเดิมจะค้างที่การ์ด "ต้องเข้าสู่ระบบก่อน"
 * แล้วต้องกดเองอีกทีว่าจะไปไหนต่อ — ตอนนี้พาไปที่ที่ทำอะไรต่อได้จริงให้เลย
 *
 * ใช้กับการ "พาไปหน้าที่ถูก" เท่านั้น ไม่ใช่การกันข้อมูล — ด่านจริงอยู่ที่ backend
 * ทุก endpoint ตรวจสิทธิ์ของตัวเองอยู่แล้ว (ดู tests/test_step11_permissions.py)
 */
type Guard = {
  match: RegExp;
  roles: Role[];
  /** ไปไหนเมื่อสิทธิ์ไม่ถึง · ใส่ %s เพื่อแนบหน้าเดิมกลับมาหลังเข้าสู่ระบบสำเร็จ */
  fallback: string;
};

const STAFF: Role[] = ["sales", "manager", "admin"];

const GUARDS: Guard[] = [
  // เครื่องมือพนักงาน — ออกจากระบบแล้วสิ่งเดียวที่ทำต่อได้คือเข้าสู่ระบบใหม่
  { match: /^\/sales(\/|$)/, roles: STAFF, fallback: "/staff?next=%s" },
  { match: /^\/manager(\/|$)/, roles: ["manager", "admin"], fallback: "/staff?next=%s" },
  // หน้าบัญชี — ออกจากระบบแล้วพากลับไปเลือกสินค้าต่อ ไม่ต้องบังคับให้ล็อกอินใหม่
  { match: /^\/account(\/|$)/, roles: ["customer", ...STAFF], fallback: "/" },
  // กำลังจะจ่ายเงินแล้วหลุด — ของยังอยู่ในตะกร้า พากลับไปที่ตะกร้าใกล้ที่สุด
  { match: /^\/checkout(\/|$)/, roles: ["customer"], fallback: "/cart" },
];

/** คืน path ที่ควรพาไป หรือ null ถ้าอยู่หน้านี้ต่อได้ */
export function redirectFor(pathname: string, role: Role): string | null {
  const g = GUARDS.find((x) => x.match.test(pathname));
  if (!g || g.roles.includes(role)) return null;
  return g.fallback.replace("%s", encodeURIComponent(pathname));
}
