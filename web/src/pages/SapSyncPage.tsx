import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Icon from "../components/Icon";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { bahtWord, relTime } from "../lib/format";
import type { SyncJob } from "../lib/types";

const LABEL: Record<string, string> = { pending: "รอส่งใหม่", failed: "ส่งไม่สำเร็จ", ok: "ส่งแล้ว" };

/** ผู้จัดการ/แอดมิน: ใบที่รับเงินแล้วแต่สร้าง Sales Order ใน SAP ไม่สำเร็จ */
export default function SapSyncPage() {
  const auth = useAuth();
  const allowed = auth.role === "manager" || auth.role === "admin";
  const [rows, setRows] = useState<SyncJob[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    apiGet<SyncJob[]>("/admin/sap-sync").then(setRows).catch((e) => setErr(errorMessage(e)));
  }, []);
  useEffect(() => {
    if (allowed) load();
  }, [allowed, load]);

  if (!allowed) {
    return (
      <main className="container sec">
        <div className="card" style={{ maxWidth: 520 }}>
          <b>คิวส่งข้อมูลเข้า SAP</b>
          <p className="muted small">เฉพาะผู้จัดการสาขา / แอดมิน</p>
          <Link className="btn dark" to="/staff">เข้าสู่ระบบพนักงาน</Link>
        </div>
      </main>
    );
  }

  const act = async (path: string, key: string) => {
    setBusy(key);
    setErr(null);
    try {
      const r = await apiPost<{ ok?: number; failed?: number; sap_so_no?: string | null }>(path);
      setMsg(r.sap_so_no ? `สร้าง SO ${r.sap_so_no} สำเร็จ` : `ประมวลผลคิวแล้ว · สำเร็จ ${r.ok ?? 0} · ยังไม่สำเร็จ ${r.failed ?? 0}`);
      load();
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const stuck = (rows || []).filter((r) => r.status !== "ok");

  return (
    <main className="container sec">
      <div className="row between wrap" style={{ marginBottom: 12 }}>
        <div>
          <h1 className="cart-title" style={{ marginBottom: 2 }}>คิวส่งข้อมูลเข้า SAP</h1>
          <p className="small muted" style={{ margin: 0 }}>ใบที่ลูกค้าจ่ายเงินแล้วแต่ยังไม่ได้เลข SO — เงินไม่หาย ระบบลองใหม่ให้อัตโนมัติ</p>
        </div>
        <button className="btn primary" disabled={busy !== null} onClick={() => act("/admin/sap-sync/run", "run")}><Icon name="sync" size={18} /> ลองส่งคิวที่ค้าง ({stuck.length})</button>
      </div>
      {err && <div className="note err" style={{ marginBottom: 10 }}>{err}</div>}
      {msg && <div className="note ok" style={{ marginBottom: 10 }}>{msg}</div>}
      {!rows && !err && <div className="ph" style={{ height: 120 }}>กำลังโหลด…</div>}
      {rows && (
        <div className="tbl-wrap card flat">
          <table className="tbl">
            <thead><tr><th>ใบเสนอราคา</th><th>ลูกค้า</th><th>ยอด</th><th>สถานะ</th><th>ข้อผิดพลาด</th><th></th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.quotation_no}>
                  <td><Link to={`/sales/quotations/${r.quotation_no}`} className="mono strong">{r.quotation_no}</Link><div className="small muted">จ่ายเมื่อ {relTime(r.paid_at)}</div></td>
                  <td>{r.customer_name || "-"}</td>
                  <td><b>{bahtWord(r.grand_total)}</b></td>
                  <td><span className={"chip " + (r.status === "ok" ? "green" : r.status === "failed" ? "red" : "light")}>{LABEL[r.status] || r.status}</span><div className="small muted">ลองแล้ว {r.attempts} ครั้ง</div></td>
                  <td className="small">{r.sap_so_no ? <b className="mono">SO {r.sap_so_no}</b> : r.last_error || "-"}</td>
                  <td>{r.status !== "ok" && <button className="btn sm" disabled={busy !== null} onClick={() => act(`/admin/sap-sync/${r.quotation_no}/retry`, r.quotation_no)}>ส่งใหม่</button>}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={6} className="muted">ไม่มีรายการค้าง</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
