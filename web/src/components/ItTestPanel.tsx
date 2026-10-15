import { useEffect, useState } from "react";
import { apiGet, apiPut, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import Icon from "./Icon";

type Profile = {
  staff_code: string; name: string; role: string; branch_code: string | null; branch_name: string | null;
  roles: Record<string, string>; branches: { code: string; name: string }[];
  sap_pernr: string | null; sap_sales_office: string | null; sap_sales_group: string | null;
};

/** โหมดทดสอบของทีม IT — สลับตำแหน่ง/สาขาของบัญชีตัวเองเพื่อลองระบบทุกมุม
 *
 * โผล่เฉพาะบัญชีในรายชื่อ IT_TEST_STAFF_CODES (หลังบ้านตอบ 403 ให้คนอื่น → ไม่แสดงอะไร)
 */
export default function ItTestPanel() {
  const auth = useAuth();
  const [p, setP] = useState<Profile | null>(null);
  const [role, setRole] = useState("");
  const [branch, setBranch] = useState("");
  const [pernr, setPernr] = useState("");
  const [office, setOffice] = useState("");
  const [group, setGroup] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const take = (x: Profile) => {
    setP(x);
    setRole(x.role);
    setBranch(x.branch_code || "");
    setPernr(x.sap_pernr || "");
    setOffice(x.sap_sales_office || "");
    setGroup(x.sap_sales_group || "");
  };
  useEffect(() => {
    if (!auth.user?.staff_code) return;
    apiGet<Profile>("/it-test/profile").then(take).catch(() => setP(null));
  }, [auth.user?.id, auth.user?.staff_code]);

  if (!p) return null;
  const sapChanged = pernr !== (p.sap_pernr || "") || office !== (p.sap_sales_office || "") || group !== (p.sap_sales_group || "");
  const changed = role !== p.role || branch !== (p.branch_code || "") || sapChanged;

  const save = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const x = await apiPut<Profile>("/it-test/profile", {
        role, branch_code: branch || null,
        ...(sapChanged ? { sap_pernr: pernr.trim(), sap_sales_office: office.trim(), sap_sales_group: group.trim() } : {}),
      });
      take(x);
      await auth.refreshMe();   // เมนู/หน้าที่เข้าได้เปลี่ยนตาม role ใหม่ทันที
      setMsg({ ok: true, text: `เปลี่ยนแล้ว — ตอนนี้เป็น ${x.roles[x.role] || x.role} · ${x.branch_name || "ไม่มีสาขา"}` });
    } catch (e) {
      setMsg({ ok: false, text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="privacy-box it-test">
      <h2><Icon name="science" size={20} /> โหมดทดสอบ IT</h2>
      <p className="small muted" style={{ marginTop: 0 }}>
        บัญชี {p.staff_code} เป็นบัญชีทดสอบ — สลับตำแหน่งและสาขาได้เองเพื่อลองระบบในมุมของแต่ละคน · ทุกครั้งที่เปลี่ยนระบบบันทึกประวัติไว้
      </p>
      <div className="it-test-row">
        <label>
          <span>ตำแหน่ง (role)</span>
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            {Object.entries(p.roles).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label>
          <span>สาขา</span>
          <select value={branch} onChange={(e) => setBranch(e.target.value)}>
            {!p.branch_code && <option value="">— ยังไม่ผูกสาขา —</option>}
            {p.branches.map((b) => <option key={b.code} value={b.code}>{b.code} · {b.name}</option>)}
          </select>
        </label>
      </div>
      <div className="it-test-sub">
        <b className="small">พนักงานขายสำหรับทดสอบ (ฝั่ง SAP)</b>
        <p className="tiny muted" style={{ margin: "2px 0 6px" }}>
          บัญชีทดสอบไม่ได้เข้าผ่าน SAP — ใส่รหัสคนขายที่จะลงใบเสนอราคาตอนเทส · ใช้ได้แค่โหมดทดสอบ (TEST) ออกเอกสารจริงไม่ได้
        </p>
        <div className="it-test-row">
          <label>
            <span>รหัสพนักงาน</span>
            <input value={pernr} onChange={(e) => setPernr(e.target.value.replace(/\D/g, "").slice(0, 8))} placeholder="เช่น 09570311" inputMode="numeric" />
          </label>
          <label>
            <span>สำนักงานขาย</span>
            <input value={office} onChange={(e) => setOffice(e.target.value.toUpperCase().slice(0, 4))} placeholder="SBDS" />
          </label>
          <label>
            <span>กลุ่มขาย</span>
            <input value={group} onChange={(e) => setGroup(e.target.value.toUpperCase().slice(0, 3))} placeholder="311" />
          </label>
        </div>
      </div>
      <div className="it-test-row">
        <button className="btn primary" disabled={!changed || busy} onClick={save}>{busy ? "กำลังเปลี่ยน…" : "บันทึก"}</button>
      </div>
      {role === "admin" && p.role !== "admin" && (
        <div className="note warn small" style={{ marginTop: 8 }}>แอดมินใช้หน้าขาย (ตะกร้า/ใบเสนอราคา) ไม่ได้ — กลับมาเปลี่ยนเป็น SA/ผู้จัดการได้ที่หน้านี้</div>
      )}
      {msg && <div className={"note small " + (msg.ok ? "ok" : "err")} style={{ marginTop: 8 }}>{msg.text}</div>}
    </section>
  );
}
