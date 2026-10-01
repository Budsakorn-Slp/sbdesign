import { useEffect, useState } from "react";
import { DEMO_ACCOUNTS, useAuth } from "../lib/auth";
import { usePublicConfig } from "../lib/publicConfig";
import AuthShell from "./AuthShell";
import CustomerLogin from "./CustomerLogin";
import Icon from "./Icon";
import MemberLink, { SHELL, type Phase } from "./MemberLink";

/** กล่องเข้าสู่ระบบของลูกค้า — เปิดทับหน้าที่กำลังทำอยู่ ไม่ต้องเปลี่ยนหน้า
 *
 * ลูกค้ามักถูกขอให้ล็อกอินกลางทาง (กดถูกใจ · จะชำระเงิน) พาไปอีกหน้าแล้วกลับมา ทำให้
 * เสียจังหวะที่กำลังทำอยู่ · หน้า /login ยังอยู่สำหรับลิงก์ตรง ส่วนพนักงานแยกไป /staff
 * เหมือนเดิม — ฟอร์มข้างในใช้คอมโพเนนต์ตัวเดียวกันทั้งสองทาง ไม่ได้เขียนซ้ำ
 *
 * จอเล็กกางเต็มจอ (ดู .modal.sheet) เพราะกล่องเล็กๆ กลางจอมือถือพิมพ์ลำบาก
 * และคีย์บอร์ดเด้งขึ้นมาทับพอดี
 */
export default function LoginModal() {
  const cfg = usePublicConfig();
  const auth = useAuth();
  const [preset, setPreset] = useState("");
  const [linking, setLinking] = useState(false);
  const [phase, setPhase] = useState<Phase>("member");

  // ปิดด้วย Esc — เป็นสิ่งที่คนคาดหวังจาก dialog และช่วยคนที่ใช้คีย์บอร์ดอย่างเดียว
  useEffect(() => {
    if (!auth.loginOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && auth.closeLogin();
    document.addEventListener("keydown", onKey);
    // กันหน้าหลังกล่องเลื่อนตามนิ้ว ตอนกล่องกางเต็มจอบนมือถือ
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [auth.loginOpen, auth.closeLogin]);

  useEffect(() => {
    if (!auth.loginOpen) setLinking(false); // ปิดแล้วเปิดใหม่ต้องเริ่มที่ขั้นกรอกเบอร์เสมอ
  }, [auth.loginOpen]);

  if (!auth.loginOpen) return null;

  const close = () => auth.closeLogin();

  return (
    <div className="modal-backdrop" onClick={close}>
      <div className="modal sheet" role="dialog" aria-modal="true" aria-label="เข้าสู่ระบบ" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head close-only">
          <button className="icon-btn" onClick={close} aria-label="ปิด"><Icon name="close" /></button>
        </div>

        {linking && auth.user ? (
          <AuthShell inModal {...SHELL[phase]}>
            <MemberLink onPhase={setPhase} onDone={close} />
          </AuthShell>
        ) : (
          <AuthShell
            inModal
            title="ยินดีต้อนรับสู่ SB"
            subtitle="เข้าสู่ระบบเพื่อสะสมแต้ม ดูประวัติการซื้อ และสั่งซื้อได้เร็วขึ้น"
          >
            <CustomerLogin
              presetPhone={preset}
              allowSignup={!cfg?.invite_only}
              allowOtp={cfg?.otp_enabled !== false}
              onDone={(u) => (u.needs_profile ? setLinking(true) : close())}
            />

            {cfg && !cfg.invite_only && (
            <>
            <div className="auth-or">เบอร์ทดสอบ</div>
            <div className="demo-accounts">
              {DEMO_ACCOUNTS.filter((d) => d.type === "customer").map((d) => (
                <button key={d.id} className="demo-row" onClick={() => setPreset(d.id)}>
                  <Icon name="person" size={20} />
                  <span><b>{d.title}</b><small>{d.id}</small></span>
                </button>
              ))}
            </div>
            </>
            )}
          </AuthShell>
        )}
      </div>
    </div>
  );
}
