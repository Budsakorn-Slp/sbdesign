import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import AuthShell from "../components/AuthShell";
import CustomerLogin from "../components/CustomerLogin";
import MemberLink, { SHELL, type Phase } from "../components/MemberLink";
import { useAuth } from "../lib/auth";

/** หน้าเข้าสู่ระบบของลูกค้า — เบอร์โทร + OTP
 *
 * เป็นหน้าจริงหน้าเดียว ไม่มีกล่องเด้งทับหน้าเดิมอีกแล้ว: กด back ได้ ส่งลิงก์ต่อได้
 * มีที่ลงให้ปุ่มจากอีเมล/SMS และไม่ต้องดูแลสองทางที่ทำเรื่องเดียวกัน
 * ?next=/cart พากลับไปที่เดิมหลังเข้าสำเร็จ จึงไม่หลุดสิ่งที่กำลังทำค้างอยู่
 */
export default function LoginPage() {
  const auth = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [linking, setLinking] = useState(false);
  const [phase, setPhase] = useState<Phase>("member");
  // รับเฉพาะ path ภายใน — ถ้าปล่อยให้เป็น URL เต็มจะกลายเป็น open redirect
  // (ส่งลิงก์ /login?next=https://เว็บปลอม แล้วคนเชื่อเพราะโดเมนต้นทางถูก)
  const raw = params.get("next") || "/";
  const next = raw.startsWith("/") && !raw.startsWith("//") ? raw : "/";

  // เพิ่งเข้าสู่ระบบสำเร็จและยังไม่เคยผ่านขั้นตั้งค่าบัญชี (user.needs_profile) → ถามให้จบ
  // ตรงนี้ครั้งเดียว · กดข้ามแล้ว backend จะบันทึก onboarded_at ไว้ ครั้งหน้าจึงไม่ถามอีก
  //
  // เงื่อนไขดูแค่ linking ไม่ดู sap_customer_no ด้วย — พอผูกสำเร็จ user มีเลขสมาชิกทันที
  // ถ้าเอามาเป็นเงื่อนไขร่วม หน้าจะกระโดดไปการ์ด "เข้าสู่ระบบอยู่แล้ว" ทันทีที่กดผูก
  // ลูกค้าจะไม่เห็นคำยืนยันว่าผูกสำเร็จเลย · ปล่อยให้ MemberLink คุมจังหวะจบของตัวเอง
  if (linking && auth.user) {
    return (
      <AuthShell {...SHELL[phase]}>
        <MemberLink onPhase={setPhase} onDone={() => nav(next, { replace: true })} />
      </AuthShell>
    );
  }

  if (auth.user) {
    return (
      <AuthShell title="เข้าสู่ระบบอยู่แล้ว" subtitle={auth.user.name}>
        <Link className="btn primary block" to={next}>ไปต่อ</Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="ยินดีต้อนรับสู่ SB"
      subtitle="เข้าสู่ระบบเพื่อสะสมแต้ม ดูประวัติการซื้อ และสั่งซื้อได้เร็วขึ้น"
    >
      <CustomerLogin onDone={(u) => (u.needs_profile ? setLinking(true) : nav(next, { replace: true }))} />
    </AuthShell>
  );
}
