import { useEffect, useState, type FormEvent } from "react";
import { apiGet, apiPut, errorMessage } from "../lib/api";
import type { Cart, EmployeeRef, StaffRole } from "../lib/types";
import Icon from "./Icon";

/** หมายเหตุหลักของบิล — ใต้รายการสินค้า (หมายเหตุรายสินค้าอยู่ที่แถวสินค้าแต่ละแถว) */
export function CartRemark({ cart, onChange }: { cart: Cart; onChange: (c: Cart) => void }) {
  const [remark, setRemark] = useState(cart.overall_remark || "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // สลับตะกร้า/อีกเครื่องแก้มา → ช่องหมายเหตุต้องตามของจริง
  useEffect(() => setRemark(cart.overall_remark || ""), [cart.id, cart.overall_remark]);

  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      onChange(await apiPut<Cart>(`/sales/carts/${cart.id}/remark`, { overall_remark: remark }));
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="cart-extra">
      <label className="ce-label" htmlFor="cart-remark"><Icon name="sticky_note_2" size={18} /> หมายเหตุหลักของบิล</label>
      <p className="tiny muted" style={{ margin: "0 0 6px" }}>ใช้กับทั้งบิล (เช่น นัดส่งก่อน 10 โมง) · หมายเหตุของสินค้าแต่ละชิ้นใส่ที่แถวสินค้า · ข้อความนี้ไปขึ้นบนใบเสนอราคา</p>
      <textarea id="cart-remark" className="ce-remark" rows={2} maxLength={1000} value={remark}
                onChange={(e) => setRemark(e.target.value)} placeholder="หมายเหตุหลัก (ไม่บังคับ)" />
      <div className="row" style={{ justifyContent: "flex-end", marginTop: 6 }}>
        <button className="btn sm" disabled={busy || remark === (cart.overall_remark || "")} onClick={save}>
          {busy ? "กำลังบันทึก…" : "บันทึกหมายเหตุ"}
        </button>
      </div>
      {err && <div className="note err small" style={{ marginTop: 6 }}>{err}</div>}
    </div>
  );
}

/** พนักงานร่วมบิล Z1-ZK — อยู่ในแถบลูกค้าด้านบน (เป็นข้อมูลของ "บิล" เหมือนลูกค้า ไม่ใช่ของสินค้าชิ้นไหน)
 *
 * กรอกรหัสพนักงาน + เลือกประเภท Z แล้วกดเพิ่ม · ชื่อดึงจากทะเบียนพนักงานเอง พิมพ์ชื่อไม่ได้
 * รหัสไม่มีในทะเบียน = เพิ่มไม่ได้ (backend ตอบ 404)
 */
export function CartCoSellers({ cart, onChange }: { cart: Cart; onChange: (c: Cart) => void }) {
  const [roles, setRoles] = useState<StaffRole[]>([]);
  const [emps, setEmps] = useState<EmployeeRef[]>([]);
  const [code, setCode] = useState("");
  const [role, setRole] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    apiGet<StaffRole[]>("/staff/roles").then(setRoles).catch(() => setRoles([]));
    apiGet<EmployeeRef[]>("/staff/employees").then(setEmps).catch(() => setEmps([]));
  }, []);

  const taken = new Set((cart.staff || []).map((s) => s.role_code));
  const free = roles.filter((r) => !taken.has(r.code));
  const match = emps.find((e) => e.employee_code.toUpperCase() === code.trim().toUpperCase());

  const put = async (role_code: string, employee_code: string | null) => {
    setBusy(role_code);
    setErr(null);
    try {
      onChange(await apiPut<Cart>(`/sales/carts/${cart.id}/staff`, { role_code, employee_code }));
      return true;
    } catch (e) {
      setErr(errorMessage(e));
      return false;
    } finally {
      setBusy(null);
    }
  };

  const add = async (e: FormEvent) => {
    e.preventDefault();
    if (!code.trim() || !role) return;
    if (await put(role, code.trim())) {
      setCode("");
      setRole("");
      setOpen(false);
    }
  };

  return (
    <div className="sess-staff">
      <span className="small sess-lbl">พนักงานร่วมบิล:</span>
      {(cart.staff || []).map((s) => (
        <span key={s.role_code} className="staff-pill" title={s.role_name}>
          <b>{s.role_code}</b> {s.employee_code} – {s.employee_name}
          <button aria-label={`เอา ${s.role_code} ออก`} disabled={busy === s.role_code} onClick={() => put(s.role_code, null)}><Icon name="close" size={14} /></button>
        </span>
      ))}
      {!open && free.length > 0 && (
        <button className="link-btn small sess-staff-add" onClick={() => setOpen(true)}><Icon name="person_add" size={16} /> เพิ่มพนักงาน</button>
      )}
      {open && (
        <form className="staff-add" onSubmit={add}>
          <input list="staff-codes" value={code} onChange={(e) => setCode(e.target.value)} placeholder="รหัสพนักงาน" autoFocus maxLength={32} aria-label="รหัสพนักงาน" />
          <datalist id="staff-codes">{emps.map((e) => <option key={e.user_id} value={e.employee_code}>{e.label}</option>)}</datalist>
          <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="ประเภทพนักงาน">
            <option value="">ประเภท Z…</option>
            {free.map((r) => <option key={r.code} value={r.code}>{r.code} · {r.name}</option>)}
          </select>
          <button className="btn sm" type="submit" disabled={!code.trim() || !role || busy !== null}>เพิ่ม</button>
          <button className="link-btn small" type="button" onClick={() => { setOpen(false); setErr(null); }}>ยกเลิก</button>
          {code.trim() && <span className="tiny staff-hint">{match ? match.employee_name : "ไม่พบรหัสนี้ในทะเบียน"}</span>}
        </form>
      )}
      {(cart.staff || []).length === 0 && !open && <span className="tiny sess-lbl">ยังไม่ระบุ</span>}
      {err && <span className="tiny staff-err">{err}</span>}
    </div>
  );
}
