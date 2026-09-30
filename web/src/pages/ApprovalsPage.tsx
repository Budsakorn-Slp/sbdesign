import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Icon from "../components/Icon";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { bahtWord, relTime } from "../lib/format";
import type { Approval } from "../lib/types";

/** ผู้จัดการสาขา: อนุมัติ/ปฏิเสธส่วนลดพนักงานที่เกินโควตา */
export default function ApprovalsPage() {
  const auth = useAuth();
  const [rows, setRows] = useState<Approval[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    apiGet<Approval[]>("/discount-approvals").then(setRows).catch((e) => setErr(errorMessage(e)));
  }, []);
  useEffect(() => {
    if (auth.role === "manager" || auth.role === "admin") load();
  }, [auth.role, load]);

  const decide = async (id: string, ok: boolean) => {
    setBusy(id);
    try {
      await apiPost(`/discount-approvals/${id}/${ok ? "approve" : "reject"}`);
      load();
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  if (auth.role !== "manager" && auth.role !== "admin") {
    return (
      <main className="container sec">
        <div className="card" style={{ maxWidth: 520 }}>
          <b>เฉพาะผู้จัดการสาขา</b>
          <p className="muted small">เข้าสู่ระบบด้วย MG-001 เพื่ออนุมัติส่วนลดเกินโควตา</p>
          <Link className="btn dark" to="/staff">เข้าสู่ระบบพนักงาน</Link>
        </div>
      </main>
    );
  }

  return (
    <main className="container sec">
      <h1 className="cart-title">คำขออนุมัติส่วนลด</h1>
      {err && <div className="note err">{err}</div>}
      {!rows && !err && <div className="ph" style={{ height: 120 }}>กำลังโหลด…</div>}
      {rows && rows.length === 0 && <div className="card flat muted">ไม่มีคำขอที่รออนุมัติ</div>}
      {rows && rows.length > 0 && (
        <div className="tbl-wrap card flat">
          <table className="tbl">
            <thead>
              <tr><th>ตะกร้า / ลูกค้า</th><th>พนักงาน</th><th>ส่วนลด</th><th>เหตุผล</th><th>ขอเมื่อ</th><th></th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td><b>{r.cart_no}</b><br /><span className="small muted">{r.customer_name || "ยังไม่ผูกลูกค้า"}</span></td>
                  <td>{r.sales_name}</td>
                  <td><b>{Number(r.percent)}%</b> · −{bahtWord(r.amount)}</td>
                  <td className="small">{r.reason || "-"}</td>
                  <td className="small muted">{relTime(r.created_at)}</td>
                  <td>
                    <div className="row">
                      <button className="btn green sm" disabled={busy === r.id} onClick={() => decide(r.id, true)}><Icon name="check" size={16} /> อนุมัติ</button>
                      <button className="btn sm" disabled={busy === r.id} onClick={() => decide(r.id, false)}>ปฏิเสธ</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
