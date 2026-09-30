import { Suspense } from "react";
import { Link, Outlet } from "react-router-dom";

/** โครงหน้าเปล่า — ไม่มีหัวเว็บ เมนูหมวด ตะกร้า หรือ footer การตลาดของฝั่งลูกค้า
 *
 * ใช้กับหน้าที่ "ไม่ใช่หน้าร้าน" อย่างทางเข้าของพนักงาน · ถ้าเอาไปวางใน Layout เดียวกับ
 * ลูกค้า มันจะมีช่องค้นหาสินค้า เมนูห้องนอน/ห้องนั่งเล่น และกล่องชวนสมัครสมาชิกขึ้นมา
 * รอบๆ ฟอร์มรหัสพนักงาน ซึ่งไม่เกี่ยวอะไรกับงานตรงหน้าเลย และทำให้ดูเป็นหน้าสาธารณะ
 */
export default function BareLayout() {
  return (
    <div className="bare">
      <header className="bare-head">
        <Link to="/" className="bare-logo" aria-label="SB Design Square">
          <img src="https://media.sbdesignsquare.com/media/logo/stores/2/Logo_header_newsb_1.png" alt="SB Design Square" />
        </Link>
      </header>
      <Suspense fallback={<div className="ph" style={{ height: 320, margin: 24, borderRadius: 12 }} />}>
        <Outlet />
      </Suspense>
      <footer className="bare-foot">
        <small>© SB Design Square · ระบบภายในสำหรับพนักงาน</small>
      </footer>
    </div>
  );
}
