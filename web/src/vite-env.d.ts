/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** คำลัดสำหรับเปิดหน้าเข้าสู่ระบบพนักงาน — พิมพ์ในช่องเบอร์โทร/อีเมลของหน้าลูกค้าแล้วกดเข้าสู่ระบบ
   *
   * เป็นแค่ "ทางลัดไปหน้า /staff" ไม่ใช่รหัสผ่านและไม่ได้กันอะไร — ค่านี้ติดไปกับไฟล์ JS
   * ที่ส่งให้ทุกคน เปิด DevTools ก็อ่านได้ · ที่ยอมรับได้เพราะถึงรู้ก็แค่ไปโผล่หน้า /staff
   * ซึ่งพิมพ์ URL ตรงๆ ก็เข้าได้อยู่แล้ว
   *
   * เปลี่ยนค่าได้ที่ web/.env (ต้อง build ใหม่) — ไม่ตั้งก็ใช้ค่าเริ่มต้น "SA-Sale"
   */
  readonly VITE_STAFF_DOOR?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
