import { useAuth } from "../lib/auth";
import Icon from "./Icon";

const ROLE: Record<string, string> = { sales: "พนักงานขาย", manager: "ผู้จัดการ", admin: "แอดมิน" };

/** หัวโปรไฟล์ของพนักงาน + ตัวตนคนขายฝั่ง SAP — ค่าชุดนี้จะลงใบเสนอราคาเป็น "คนขาย"
 *
 * sap = SAP ยืนยันจากรหัส+PIN แล้ว · local = บัญชีทดสอบ ค่าตั้งเองในโหมดทดสอบ IT (ใช้ได้แค่ TEST)
 */
export default function StaffSapCard() {
  const u = useAuth().user;
  if (!u || u.role === "customer") return null;
  const sap = u.auth_source === "sap";
  const initials = (u.name || "?").trim().slice(0, 1);
  const items: [string, string, string | null | undefined][] = [
    ["badge", "รหัสพนักงาน SAP", u.sap_pernr],
    ["apartment", "สำนักงานขาย", u.sap_sales_office],
    ["groups", "กลุ่มขาย (showroom)", u.sap_sales_group],
    ["storefront", "สาขาในระบบเว็บ", u.branch_id],
  ];
  return (
    <section className="privacy-box staff-card">
      <div className="staff-head">
        <span className="staff-avatar">{initials}</span>
        <div className="staff-who">
          <b>{u.name}</b>
          <span className="small muted">{ROLE[u.role] || u.role} · รหัส {u.staff_code}</span>
        </div>
        <span className={"staff-src " + (sap ? "sap" : "local")}>
          <Icon name={sap ? "verified_user" : "science"} size={15} />
          {sap ? "ยืนยันจาก SAP" : "บัญชีทดสอบ"}
        </span>
      </div>

      <h3 className="staff-sub">ข้อมูลพนักงานขาย</h3>
      <div className="staff-grid">
        {items.map(([icon, label, v]) => (
          <div key={label} className="staff-tile">
            <span className="staff-tile-lbl"><Icon name={icon} size={15} /> {label}</span>
            <b className={v ? "" : "muted"}>{v || "ยังไม่มี"}</b>
          </div>
        ))}
      </div>
      {!sap && (
        <p className="tiny muted" style={{ margin: "10px 0 0" }}>
          บัญชีทดสอบไม่ได้เข้าผ่าน SAP — ตั้งค่าได้ในโหมดทดสอบ IT ด้านล่าง ใช้เทสได้แต่ออกเอกสารจริงไม่ได้
        </p>
      )}
    </section>
  );
}
