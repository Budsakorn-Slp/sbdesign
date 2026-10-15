import { useAuth } from "../lib/auth";
import Icon from "./Icon";

/** ตัวตนคนขายฝั่ง SAP ของพนักงานที่ล็อกอินอยู่ — ค่าชุดนี้จะลงใบเสนอราคาเป็น "คนขาย"
 *
 * sap = SAP ยืนยันจากรหัส+PIN แล้ว · local = บัญชีทดสอบ ค่าตั้งเองในโหมดทดสอบ IT (ใช้ได้แค่ TEST)
 */
export default function StaffSapCard() {
  const u = useAuth().user;
  if (!u || u.role === "customer") return null;
  const sap = u.auth_source === "sap";
  const dash = (v?: string | null) => v || "—";
  return (
    <section className="privacy-box">
      <h2><Icon name="badge" size={20} /> ข้อมูลพนักงานขาย (SAP)</h2>
      <p className="small muted" style={{ margin: 0 }}>
        {sap
          ? "เข้าสู่ระบบด้วยรหัสพนักงาน + PIN ของ SAP — ข้อมูลชุดนี้มาจาก SAP และจะลงใบเสนอราคาเป็นคนขาย"
          : "บัญชีทดสอบ (ไม่ได้เข้าผ่าน SAP) — ค่าด้านล่างตั้งเองในโหมดทดสอบ IT ใช้เทสได้ แต่ออกเอกสารจริงไม่ได้"}
      </p>
      <div className="sap-id">
        <div>รหัสพนักงาน SAP<b className="mono">{dash(u.sap_pernr)}</b></div>
        <div>สำนักงานขาย<b>{dash(u.sap_sales_office)}</b></div>
        <div>กลุ่มขาย (showroom)<b>{dash(u.sap_sales_group)}</b></div>
        <div>สาขาในระบบเว็บ<b>{dash(u.branch_id)}</b></div>
      </div>
    </section>
  );
}
