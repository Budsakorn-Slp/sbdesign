import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Icon from "../components/Icon";
import QuotationShare from "../components/QuotationShare";
import { API_BASE, apiGet, apiPost, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { bahtWord, relTime } from "../lib/format";
import { useSales } from "../lib/sales";
import type { PresoSummary, Quotation } from "../lib/types";

/** S5 · Preso ที่เซฟไว้ — ดึงกลับมาทำต่อ / สร้าง Quotation / ดูใบเสนอราคาที่ออกแล้ว */
/** ลิงก์เอกสาร — เปิดแท็บใหม่จึงต้องพ่วง token มาเอง (แท็บใหม่ไม่มี Authorization header) */
function docUrl(p: PresoSummary, withImages: boolean): string {
  const qs = new URLSearchParams();
  if (p.quotation_token) qs.set("t", p.quotation_token);
  if (withImages) qs.set("images", "1");
  return `${API_BASE}/quotations/${p.quotation_no}/document?${qs.toString()}`;
}

export default function PresosPage() {
  const auth = useAuth();
  const sales = useSales();
  const nav = useNavigate();
  const [tab, setTab] = useState<"draft" | "quoted">("draft");
  const [rows, setRows] = useState<PresoSummary[] | null>(null);
  const [quotes, setQuotes] = useState<Quotation[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [share, setShare] = useState<{ no: string; token: string | null } | null>(null);
  // บิลรวม: ติ๊กใบรอชำระของลูกค้าคนเดียวกัน แล้วไปชำระรวมครั้งเดียว
  const [picked, setPicked] = useState<PresoSummary[]>([]);

  const load = useCallback(() => {
    if (!sales.enabled) return;
    apiGet<PresoSummary[]>("/presos?mine=true").then(setRows).catch((e) => setErr(errorMessage(e)));
    apiGet<Quotation[]>("/quotations").then(setQuotes).catch(() => setQuotes([]));
  }, [sales.enabled]);
  useEffect(load, [load]);

  if (!sales.enabled) {
    return (
      <main className="container sec">
        <div className="card" style={{ maxWidth: 520 }}>
          <b>Preso ของฉัน</b>
          <p className="muted small">ต้องเข้าสู่ระบบด้วยบัญชีพนักงานขาย</p>
          <Link className="btn dark" to="/staff">เข้าสู่ระบบพนักงาน</Link>
        </div>
      </main>
    );
  }

  const drafts = (rows || []).filter((r) => r.status === "draft");
  const quoted = (rows || []).filter((r) => r.status !== "draft");

  const reopen = async (p: PresoSummary) => {
    setBusy(p.id);
    setErr(null);
    try {
      await apiPost(`/presos/${p.preso_no}/reopen`);
      await sales.reload();
      sales.setActiveId(p.cart_id);
      nav("/sales");
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const makeQuotation = async (p: PresoSummary, force = false) => {
    setBusy(p.id);
    setErr(null);
    try {
      const q = await apiPost<Quotation>(`/presos/${p.preso_no}/quotation`, { force });
      nav(`/sales/quotations/${q.quotation_no}`);
    } catch (e) {
      const detail = (e as { detail?: { shortages?: { name: string; need: number; available: number }[]; message?: string } }).detail;
      if (detail && typeof detail === "object" && detail.shortages) {
        const lines = detail.shortages.map((s) => `• ${s.name}: ต้องการ ${s.need} มี ${s.available}`).join("\n");
        if (confirm(`${detail.message}\n\n${lines}\n\nออกใบเสนอราคาทั้งที่ของไม่พอ?`)) return makeQuotation(p, true);
      } else setErr(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <main className="container sec">
      <div className="row between wrap" style={{ marginBottom: 12 }}>
        <h1 className="cart-title" style={{ marginBottom: 0 }}>Preso ของฉัน</h1>
        <div className="seg" style={{ margin: 0, width: 360 }}>
          <button className={"seg-btn" + (tab === "draft" ? " on" : "")} onClick={() => setTab("draft")}>ร่าง {drafts.length}</button>
          <button className={"seg-btn" + (tab === "quoted" ? " on" : "")} onClick={() => setTab("quoted")}>ออก Quotation แล้ว {quoted.length}</button>
        </div>
      </div>
      {err && <div className="note err" style={{ marginBottom: 10 }}>{err}</div>}
      {!rows && !err && <div className="ph" style={{ height: 120 }}>กำลังโหลด…</div>}
      {rows && (
        <div className="tbl-wrap card flat">
          <table className="tbl">
            <thead>
              <tr>{tab === "quoted" && <th style={{ width: 36 }}></th>}<th>เลขที่ / ลูกค้า</th><th>สินค้า</th><th>ยอด</th><th>อัปเดต</th><th></th></tr>
            </thead>
            <tbody>
              {(tab === "draft" ? drafts : quoted).map((p) => (
                <tr key={p.id} className={picked.some((x) => x.id === p.id) ? "picked" : ""}>
                  {tab === "quoted" && (
                    <td>
                      {p.quotation_status === "issued" && p.quotation_no && (
                        <input type="checkbox" aria-label={`เลือก ${p.quotation_no} เข้าบิลรวม`}
                          checked={picked.some((x) => x.id === p.id)}
                          // บิลรวมต้องเป็นลูกค้าคนเดียวกัน — ติ๊กใบแรกแล้ว ใบของลูกค้าอื่นติ๊กไม่ได้
                          disabled={picked.length > 0 && picked[0].customer_id !== p.customer_id}
                          title={picked.length > 0 && picked[0].customer_id !== p.customer_id ? "บิลรวมได้เฉพาะลูกค้าคนเดียวกัน" : ""}
                          onChange={(e) => setPicked((cur) => e.target.checked ? [...cur, p] : cur.filter((x) => x.id !== p.id))} />
                      )}
                    </td>
                  )}
                  <td>
                    <b className="mono">{p.preso_no}</b>{p.quotation_no && <> → <Link to={`/sales/quotations/${p.quotation_no}`} className="mono strong">{p.quotation_no}</Link></>}
                    <br /><span className="small muted">{p.customer_name || "ยังไม่ผูกลูกค้า"}{p.note ? ` · ${p.note}` : ""}</span>
                  </td>
                  <td>{p.item_count} ชิ้น</td>
                  <td><b>{bahtWord(p.grand_total)}</b>{p.quotation_status && <div className="small muted">{QSTATUS[p.quotation_status] || p.quotation_status}</div>}
                    {p.big_bill_no && <Link to={`/sales/bigbill/${p.big_bill_no}`} className="bb-tag" title="ใบนี้อยู่ในบิลรวมที่ยังไม่ชำระ — กดไปหน้าบิล">บิลรวม {p.big_bill_no}</Link>}</td>
                  <td className="small muted">{relTime(p.updated_at)}</td>
                  <td>
                    <div className="row">
                      {p.status === "draft" ? (
                        <>
                          <button className="btn sm" disabled={busy === p.id} onClick={() => reopen(p)}>เปิด</button>
                          <button className="btn primary sm" disabled={busy === p.id} onClick={() => makeQuotation(p)}>สร้าง Quotation</button>
                        </>
                      ) : (
                        <>
                          {p.quotation_no && <a href={docUrl(p, true)} target="_blank" rel="noreferrer" className="btn sm" title="เปิดดูใบเสนอราคาแบบมีรูปสินค้า (ดาวน์โหลดไฟล์ใช้ปุ่ม แชร์ / ดาวน์โหลด)">Preview มีรูป</a>}
                          {p.quotation_no && <a href={docUrl(p, false)} target="_blank" rel="noreferrer" className="btn sm" title="เปิดดูใบเสนอราคาแบบไม่มีรูปสินค้า">Preview ไม่มีรูป</a>}
                          {p.quotation_no && <button className="btn sm" title="ส่งเป็นไฟล์ PDF ทาง LINE/Messenger หรือดาวน์โหลด" onClick={() => setShare({ no: p.quotation_no!, token: p.quotation_token })}>แชร์ / ดาวน์โหลด</button>}
                          {p.quotation_no && p.quotation_status === "issued" && <Link to={`/sales/quotations/${p.quotation_no}`} className="btn primary sm">ไปจ่ายเงิน</Link>}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {(tab === "draft" ? drafts : quoted).length === 0 && <tr><td colSpan={6} className="muted">ไม่มีรายการ</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      <p className="small muted" style={{ marginTop: 10 }}>Preso = ใบร่างที่ยังแก้ได้ · Quotation = ล็อกราคา/โปร แล้วส่งต่อให้ระบบ SAP{quotes.length ? ` · ใบเสนอราคาทั้งหมดของฉัน ${quotes.length} ใบ` : ""}</p>
      <div className="row" style={{ marginTop: 6 }}><Icon name="arrow_back" size={16} /> <Link to="/sales">กลับไปตะกร้าที่กำลังดูแล</Link></div>
      {share && <QuotationShare no={share.no} token={share.token} staff onClose={() => setShare(null)} />}
      {tab === "quoted" && picked.length > 0 && (
        <div className="bb-bar">
          <div>
            <b>เลือก {picked.length} ใบ · {picked[0].customer_name}</b>
            <span>รวม {bahtWord(picked.reduce((n, p) => n + Number(p.grand_total), 0))} · ในหน้าถัดไปเพิ่มใบอื่นของลูกค้าคนนี้ได้</span>
          </div>
          <button className="link-btn small" onClick={() => setPicked([])}>ล้าง</button>
          <button className="btn primary" onClick={() => nav(`/sales/bigbill?q=${picked.map((p) => p.quotation_no).join(",")}`)}>
            <Icon name="receipt_long" size={18} /> ชำระรวม (Big Bill)
          </button>
        </div>
      )}
    </main>
  );
}

export const QSTATUS: Record<string, string> = { issued: "รอชำระ", paid: "ชำระแล้ว", converted: "สร้าง SO แล้ว", cancelled: "ยกเลิก", expired: "หมดอายุ" };
