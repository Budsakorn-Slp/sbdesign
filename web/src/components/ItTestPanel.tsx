import { useEffect, useState } from "react";
import { apiGet, apiPut, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import Icon from "./Icon";

type Profile = {
  staff_code: string; name: string; role: string; branch_code: string | null; branch_name: string | null;
  roles: Record<string, string>; branches: { code: string; name: string }[];
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
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const take = (x: Profile) => {
    setP(x);
    setRole(x.role);
    setBranch(x.branch_code || "");
  };
  useEffect(() => {
    if (!auth.user?.staff_code) return;
    apiGet<Profile>("/it-test/profile").then(take).catch(() => setP(null));
  }, [auth.user?.id, auth.user?.staff_code]);

  if (!p) return null;
  const changed = role !== p.role || branch !== (p.branch_code || "");

  const save = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const x = await apiPut<Profile>("/it-test/profile", { role, branch_code: branch || null });
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
        <button className="btn primary" disabled={!changed || busy} onClick={save}>{busy ? "กำลังเปลี่ยน…" : "เปลี่ยน"}</button>
      </div>
      {role === "admin" && p.role !== "admin" && (
        <div className="note warn small" style={{ marginTop: 8 }}>แอดมินใช้หน้าขาย (ตะกร้า/ใบเสนอราคา) ไม่ได้ — กลับมาเปลี่ยนเป็น SA/ผู้จัดการได้ที่หน้านี้</div>
      )}
      {msg && <div className={"note small " + (msg.ok ? "ok" : "err")} style={{ marginTop: 8 }}>{msg.text}</div>}
    </section>
  );
}
