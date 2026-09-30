import { Suspense, useEffect } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import BackToTop from "../BackToTop";
import LoginModal from "../LoginModal";
import { useCart } from "../../lib/cart";
import { usePrefetchForRole } from "../../lib/prefetch";
import { redirectFor } from "../../lib/routes";
import { trackPageView } from "../../lib/track";
import { useSales } from "../../lib/sales";
import Footer from "./Footer";
import Header from "./Header";

/** โครงหน้าเปล่าระหว่างโหลดโค้ดของหน้านั้น — สูงพอให้ footer ไม่กระโดดขึ้นมากลางจอ */
function PageFallback() {
  return (
    <main className="container sec" aria-busy="true">
      <div className="ph" style={{ height: 28, width: 220, marginBottom: 16 }} />
      <div className="ph" style={{ height: 360 }} />
    </main>
  );
}

export default function Layout() {
  const { count } = useCart();
  const sales = useSales();
  const auth = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  // พนักงานเปิดมาก็ต้องเข้าหน้าตะกร้า/ใบเสนอราคาอยู่แล้ว — โหลดโค้ดรอไว้ตอนเบราว์เซอร์ว่าง
  usePrefetchForRole(auth.role);

  // ค้างอยู่หน้าที่สิทธิ์ไม่ถึงแล้ว → พาไปหน้าที่ทำต่อได้ทันที
  // ทำงานกับทั้งสองกรณี เพราะทั้งคู่จบลงที่ role เปลี่ยนเหมือนกัน:
  //   1) กดออกจากระบบเองทั้งที่เปิดหน้าตะกร้าเซลล์ค้างไว้
  //   2) session หมดอายุ/refresh token ใช้ไม่ได้ แล้วแอปถีบกลับเป็น guest เอง
  // replace: true เพื่อไม่ให้กดย้อนกลับแล้ววนกลับมาหน้าที่เข้าไม่ได้อีก
  // เก็บสถิติว่าเปิดหน้าไหน — รอให้รู้ตัวตนก่อน (auth.ready) จะได้ผูกกับบัญชีถูกคน
  // ยิงตาม pathname อย่างเดียว ไม่รวม search string ที่เปลี่ยนทุกครั้งที่ติ๊กตัวกรอง
  // (ไม่งั้นเลื่อนหน้าค้นหาทีเดียวได้ page_view สิบแถว)
  useEffect(() => {
    if (auth.ready) trackPageView(loc.pathname);
  }, [auth.ready, loc.pathname]);

  useEffect(() => {
    if (!auth.ready) return; // ระหว่างเช็ค token อยู่ ทุกคนยังเป็น guest ชั่วคราว อย่าเพิ่งเด้ง
    const to = redirectFor(loc.pathname, auth.role);
    if (to) nav(to, { replace: true });
  }, [auth.ready, auth.role, loc.pathname, nav]);
  // กดเข้าหมวดใหม่/เปลี่ยนตัวกรอง ต้องเริ่มอ่านจากบนสุดเสมอ — ไม่ใช่ค้างอยู่ตรงที่เพิ่งเลื่อนมา
  // ผูกกับ search ด้วย เพราะหน้าค้นหาเปลี่ยนหมวด/ตัวกรองผ่าน query string ไม่ได้เปลี่ยน pathname
  // ใช้แบบกระโดดทันที ไม่ใช่เลื่อนนุ่ม — ตอนเปลี่ยนหน้าเนื้อหาเก่ากำลังจะหายอยู่แล้ว
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [loc.pathname, loc.search]);

  const salesCount = sales.enabled ? sales.sessions.reduce((n, s) => n + s.count, 0) : 0;
  return (
    <div className="app">
      <Header cartCount={sales.enabled ? salesCount : count} cartHref={sales.enabled ? "/sales" : "/cart"} />
      {/* Suspense อยู่ตรงนี้ ไม่ใช่ครอบทั้งแอป — หัวเว็บกับเมนูจึงขึ้นทันทีระหว่างรอโค้ดของหน้า
          ที่เพิ่งกดเข้าไป (ดู route ที่แยกไฟล์ใน App.tsx) ผู้ใช้ไม่เห็นจอขาวทั้งหน้า */}
      <div className="app-body">
        <Suspense fallback={<PageFallback />}>
          <Outlet />
        </Suspense>
      </div>
      <Footer />
      <BackToTop />
      <LoginModal />
    </div>
  );
}
