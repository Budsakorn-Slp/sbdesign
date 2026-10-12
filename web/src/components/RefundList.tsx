import { useEffect, useState } from "react";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import { bahtWord, thDateTime } from "../lib/format";
import Icon from "./Icon";

type Refund = {
  payment_no: string; quotation_no: string; big_bill_no: string | null; customer_name: string | null; method: string;
  amount: string; refund_due: string; refund_note: string | null; paid_at: string | null; refunded_at: string | null;
};

/** เงินที่รับซ้ำ รอคืนลูกค้า (ผู้จัดการ) — เกิดเมื่อใบถูกชำระทางอื่นไปก่อนแล้วธนาคารยังรับเงินอีกรายการเข้ามา
 *  ระบบไม่แตะใบ ไม่สร้าง SO ซ้ำ แค่บันทึกไว้ให้คนคืนเงิน แล้วกด "คืนแล้ว" */
export default function RefundList() {
  const [rows, setRows] = useState<Refund[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => { apiGet<Refund[]>("/admin/refunds").then(setRows).catch((e) => setErr(errorMessage(e))); }, []);

  const done = async (r: Refund) => {
    if (!confirm(`บันทึกว่าคืนเงิน ${bahtWord(r.refund_due)} ให้ ${r.customer_name || "ลูกค้า"} แล้ว?`)) return;
    setBusy(r.payment_no);
    try {
      const x = await apiPost<Refund>(`/admin/refunds/${r.payment_no}/done`, {});
      setRows((cur) => (cur || []).map((y) => (y.payment_no === x.payment_no ? x : y)));
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const open = (rows || []).filter((r) => !r.refunded_at);
  return (
    <section className="card" style={{ marginTop: 18 }}>
      <h2 style={{ margin: "0 0 4px", display: "flex", alignItems: "center", gap: 6, fontSize: 18 }}>
        <Icon name="currency_exchange" size={20} /> รับเงินซ้ำ รอคืนเงิน {open.length > 0 && <span className="bb-att failed">{open.length} รายการ</span>}
      </h2>
      <p className="small muted" style={{ margin: "0 0 10px" }}>ใบถูกชำระทางอื่นไปก่อน แล้วยังมีเงินอีกรายการเข้ามา — ระบบไม่สร้าง SO ซ้ำ ต้องคืนเงินลูกค้าแล้วกด "คืนแล้ว"</p>
      {err && <div className="note err small">{err}</div>}
      {rows === null ? <div className="small muted">กำลังโหลด…</div> : rows.length === 0 ? <div className="small muted">ไม่มีรายการ</div> : (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>รายการชำระ</th><th>ลูกค้า / ใบ</th><th>สาเหตุ</th><th className="r">ต้องคืน</th><th>สถานะ</th><th></th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.payment_no} className={r.refunded_at ? "bb-void-row" : ""}>
                  <td className="small"><b className="mono">{r.payment_no}</b><div className="tiny muted">{thDateTime(r.paid_at)} · {r.method}</div></td>
                  <td className="small">{r.customer_name || "-"}<div className="tiny muted">{r.big_bill_no ? `บิลรวม ${r.big_bill_no}` : r.quotation_no}</div></td>
                  <td className="tiny">{r.refund_note}</td>
                  <td className="r"><b>{bahtWord(r.refund_due)}</b>{r.refund_due !== r.amount && <div className="tiny muted">จากยอด {bahtWord(r.amount)}</div>}</td>
                  <td className="small">{r.refunded_at ? <span className="bb-att paid">คืนแล้ว {thDateTime(r.refunded_at)}</span> : <span className="bb-att failed">รอคืน</span>}</td>
                  <td>{!r.refunded_at && <button className="btn sm" disabled={busy === r.payment_no} onClick={() => done(r)}>คืนแล้ว</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
