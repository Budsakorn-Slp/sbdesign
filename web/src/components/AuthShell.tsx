import type { ReactNode } from "react";

/** โครงหน้าเข้าสู่ระบบ — ตราสัญลักษณ์ในวงกลม + หัวเรื่อง + การ์ดขาวบนพื้นไล่สี
 *
 * ใช้ร่วมกันทั้งหน้าลูกค้า หน้าพนักงาน และกล่องที่เปิดทับหน้าเดิม เพื่อให้ทั้งสามทาง
 * หน้าตาเป็นชุดเดียวกัน · ในกล่อง (inModal) ตัดพื้นหลังกับเงาออก เพราะตัวกล่องมีอยู่แล้ว
 */
export default function AuthShell({
  title,
  subtitle,
  children,
  footer,
  inModal,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
  inModal?: boolean;
}) {
  const body = (
    <div className={"auth-card" + (inModal ? " plain" : "")}>
      <div className="auth-brand">
        {/* ไฟล์โลโก้เป็นแนวยาว (ตัวมาร์ค + ตัวอักษร "DESIGN SQUARE") ใส่ทั้งภาพลงวงกลม
            จะเหลือเล็กจนอ่านไม่ออก · จึงครอบให้เห็นเฉพาะตัวมาร์ค โดยวัดจากไฟล์จริง:
            ภาพ 722×202 ตัวมาร์คจบที่ x=261 (36%) → กรอบครอบจึงเป็นอัตราส่วน 261:202 */}
        <span className="auth-logo">
          <span className="auth-logo-mark">
            <img src="https://media.sbdesignsquare.com/media/logo/stores/2/Logo_header_newsb_1.png" alt="SB Design Square" />
          </span>
        </span>
      </div>
      <h1 className="auth-title">{title}</h1>
      {subtitle && <p className="auth-sub">{subtitle}</p>}
      {children}
      {footer && <div className="auth-foot">{footer}</div>}
    </div>
  );

  return inModal ? body : <main className="auth-page">{body}</main>;
}
