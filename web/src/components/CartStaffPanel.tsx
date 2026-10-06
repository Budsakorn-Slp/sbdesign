import { useEffect, useState } from "react";
import { apiGet, apiPut, errorMessage } from "../lib/api";
import type { Cart, EmployeeRef, StaffRole } from "../lib/types";
import Icon from "./Icon";

/** หมายเหตุหลักของบิล + พนักงานร่วมบิล Z1-ZK
 *
 * พนักงานเลือกจาก dropdown "รหัส – ชื่อ" เท่านั้น ไม่มีช่องพิมพ์ชื่อเอง
 * หน้าเว็บส่งไปแค่ user_id — ชื่อกับรหัสที่ลงบิล backend ดึงจากทะเบียนพนักงานเอง
 */
export default function CartStaffPanel({ cart, onChange }: { cart: Cart; onChange: (c: Cart) => void }) {
  const [roles, setRoles] = useState<StaffRole[]>([]);
  const [emps, setEmps] = useState<EmployeeRef[]>([]);
  const [remark, setRemark] = useState(cart.overall_remark || "");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    apiGet<StaffRole[]>("/staff/roles").then(setRoles).catch(() => setRoles([]));
    apiGet<EmployeeRef[]>("/staff/employees").then(setEmps).catch(() => setEmps([]));
  }, []);
  // สลับตะกร้า/อีกเครื่องแก้มา → ช่องหมายเหตุต้องตามของจริง
  useEffect(() => setRemark(cart.overall_remark || ""), [cart.id, cart.overall_remark]);

  const saveRemark = async () => {
    setBusy("remark");
    setErr(null);
    try {
      onChange(await apiPut<Cart>(`/sales/carts/${cart.id}/remark`, { overall_remark: remark }));
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const setStaff = async (role_code: string, user_id: string) => {
    setBusy(role_code);
    setErr(null);
    try {
      onChange(await apiPut<Cart>(`/sales/carts/${cart.id}/staff`, { role_code, user_id: user_id || null }));
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const current = (code: string) => cart.staff?.find((s) => s.role_code === code);

  return (
    <div className="cart-extra">
      <label className="ce-label" htmlFor="cart-remark"><Icon name="sticky_note_2" size={18} /> หมายเหตุหลักของบิล</label>
      <p className="tiny muted" style={{ margin: "0 0 6px" }}>ใช้กับทั้งบิล (เช่น นัดส่งก่อน 10 โมง) · หมายเหตุของสินค้าแต่ละชิ้นใส่ที่แถวสินค้า · ข้อความนี้ไปขึ้นบนใบเสนอราคา</p>
      <textarea id="cart-remark" className="ce-remark" rows={2} maxLength={1000} value={remark}
                onChange={(e) => setRemark(e.target.value)} placeholder="หมายเหตุหลัก (ไม่บังคับ)" />
      <div className="row" style={{ justifyContent: "flex-end", marginTop: 6 }}>
        <button className="btn sm" disabled={busy === "remark" || remark === (cart.overall_remark || "")} onClick={saveRemark}>
          {busy === "remark" ? "กำลังบันทึก…" : "บันทึกหมายเหตุ"}
        </button>
      </div>

      <div className="ce-label" style={{ marginTop: 12 }}><Icon name="groups" size={18} /> พนักงานร่วมบิล</div>
      <div className="ce-staff">
        {roles.map((r) => {
          const cur = current(r.code);
          return (
            <label key={r.code} className="ce-role">
              <span><b>{r.code}</b> <small className="muted">{r.name}</small></span>
              <select value={cur?.user_id || ""} disabled={busy === r.code} onChange={(e) => setStaff(r.code, e.target.value)}>
                <option value="">— ไม่ระบุ —</option>
                {/* คนที่ถูกเลือกไว้แต่หายจากทะเบียนแล้ว ยังต้องโชว์ ไม่งั้นช่องจะดูเหมือนว่าง */}
                {cur && !emps.some((e) => e.user_id === cur.user_id) && <option value={cur.user_id || ""}>{cur.employee_code} – {cur.employee_name}</option>}
                {emps.map((e) => <option key={e.user_id} value={e.user_id}>{e.label}</option>)}
              </select>
            </label>
          );
        })}
      </div>
      {err && <div className="note err small" style={{ marginTop: 6 }}>{err}</div>}
    </div>
  );
}
