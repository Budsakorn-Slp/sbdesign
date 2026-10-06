import { openGoogleSheet } from "../lib/gsheet";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import Icon from "../components/Icon";
import QuotationShare from "../components/QuotationShare";
import { API_BASE, apiGet, apiPost, errorMessage } from "../lib/api";
import { usePublicConfig } from "../lib/publicConfig";
import { useAuth } from "../lib/auth";
import { SUPPLY_LABEL } from "../lib/cart";
import { bahtWord, thDate, thTime } from "../lib/format";
import type { Quotation } from "../lib/types";
import { QSTATUS } from "./PresosPage";

/** S6 (เซลล์) + C2 (ลูกค้าเปิดจากลิงก์ SMS/อีเมล ?t=token) · ใบเสนอราคา + ไปจ่ายเงิน */
export default function QuotationPage({ mode }: { mode: "sales" | "customer" }) {
  const cfg = usePublicConfig();
  const { no = "" } = useParams();
  const [params] = useSearchParams();
  const token = params.get("t");
  const auth = useAuth();
  const nav = useNavigate();
  const [q, setQ] = useState<Quotation | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [shareOpen, setShareOpen] = useState(false);

  const path = `/quotations/${no}${token ? `?t=${encodeURIComponent(token)}` : ""}`;
  const load = useCallback(() => {
    apiGet<Quotation>(path).then(setQ).catch((e) => setErr(errorMessage(e)));
  }, [path]);
  useEffect(() => {
    if (auth.ready) load();
  }, [load, auth.ready, auth.user?.id]);

  if (err) return <main className="container sec"><div className="note err">{err}</div>{!auth.user && <button className="btn dark" style={{ marginTop: 10 }} onClick={auth.openLogin}>เข้าสู่ระบบ</button>}</main>;
  if (!q) return <main className="container sec"><div className="ph" style={{ height: 240 }}>กำลังโหลดใบเสนอราคา…</div></main>;

  const isStaff = mode === "sales" && (auth.role === "sales" || auth.role === "manager");
  const docUrl = `${API_BASE}${q.pdf_url}${q.link_token ? `?t=${q.link_token}` : token ? `?t=${token}` : ""}`;
  const tk = q.link_token || token;
  const exportUrl = (format: "xlsx" | "csv") => `${API_BASE}/quotations/${q.quotation_no}/export?format=${format}${tk ? `&t=${tk}` : ""}`;
  const shareLink = q.link_token ? `${location.origin}/q/${q.quotation_no}?t=${q.link_token}` : null;

  const send = async (channel: "email" | "sms") => {
    setBusy(channel);
    try {
      const r = await apiPost<{ to: string; link: string }>(`/quotations/${q.quotation_no}/send`, { channel });
      setMsg(`ส่ง${channel === "email" ? "อีเมล" : " SMS"}ให้ ${r.to} แล้ว (mock ลง log) · ลิงก์: ${location.origin}${r.link}`);
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };
  const cancel = async () => {
    const reason = prompt("เหตุผลที่ยกเลิก (ตะกร้าจะกลับมาแก้ได้ แล้วออกใบใหม่)") ?? "";
    setBusy("cancel");
    try {
      await apiPost(`/quotations/${q.quotation_no}/cancel`, { reason });
      nav("/sales");
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const feeTotal = Number(q.shipping_fee) + Number(q.install_fee) - Number(q.shipping_discount);
  const payHref = `/pay/${q.quotation_no}${token ? `?t=${token}` : ""}`;

  return (
    <main className="container sec quotation">
      {isStaff && <Link to="/sales/presos" className="row small muted" style={{ marginBottom: 10 }}><Icon name="arrow_back" size={18} /> Preso ของฉัน</Link>}
      <div className="cart-grid">
        <div className="cart-main">
          <div className="row between wrap">
            <div>
              <div className="small muted">ใบเสนอราคา</div>
              <h1 className="cart-title" style={{ marginBottom: 2 }}>{q.quotation_no}</h1>
              <div className="small">ยืนราคาถึง <b>{thDate(q.valid_until, true)}</b> · <span className={"chip " + (q.status === "paid" || q.status === "converted" ? "green" : q.status === "cancelled" ? "red" : "light")}>{QSTATUS[q.status] || q.status}</span></div>
            </div>
            <div className="small muted" style={{ textAlign: "right" }}>
              ออกเมื่อ {thDate(q.issued_at)} {thTime(q.issued_at)}<br />{q.sales_name ? `พนักงานขาย ${q.sales_name} (${q.sales_code})` : "สั่งซื้อออนไลน์"}
            </div>
          </div>

          <div className="card flat" style={{ marginTop: 14 }}>
            <div className="row between wrap">
              <div><b>{q.customer.name}</b> · CUST {q.customer.sap_customer_no || "-"} · {(q.customer.points || 0).toLocaleString()} พ้อยท์<div className="small muted">{q.customer.phone} · {q.customer.email}</div></div>
              <div className="small muted" style={{ textAlign: "right" }}>{q.ship_address || "-"} {q.ship_postcode}<br />{q.slot_date ? `นัดส่ง ${thDate(q.slot_date)} ${q.slot_period === "am" ? "รอบเช้า" : "รอบบ่าย"}` : "ไม่มีรายการจัดส่ง"}</div>
            </div>
          </div>

          {q.stock_warnings && q.stock_warnings.length > 0 && (
            <div className="note warn" style={{ marginTop: 10 }}>
              {q.stock_warnings.some((s) => s.sap_error) ? "ออกเอกสารโดยไม่ได้เช็คสต็อก" : "ออกเอกสารทั้งที่สต็อกไม่พอ"}:{" "}
              {q.stock_warnings.map((s) => (s.sap_error ? s.name : `${s.name} (ต้องการ ${s.need} มี ${s.available})`)).join(", ")}
            </div>
          )}

          <table className="tbl" style={{ marginTop: 14 }}>
            <thead><tr><th>รายการ</th><th>รับสินค้า</th><th style={{ textAlign: "right" }}>จำนวน</th><th style={{ textAlign: "right" }}>รวม</th></tr></thead>
            <tbody>
              {q.lines.map((l) => (
                <tr key={l.matnr + l.supply_mode}>
                  <td><b>{l.name}</b><div className="small muted">{l.variant} · MATNR {l.matnr}{l.added_by === "sales" ? " · เซลล์เพิ่ม" : ""}</div></td>
                  <td className="small">{SUPPLY_LABEL[l.supply_mode]}{l.atp_date ? ` · ATP ${thDate(l.atp_date)}` : ""}</td>
                  <td style={{ textAlign: "right" }}>×{l.qty}</td>
                  <td style={{ textAlign: "right" }}><b>{bahtWord(l.line_total)}</b></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="row wrap" style={{ marginTop: 14, gap: 8 }}>
            <a className="btn sm" href={docUrl} target="_blank" rel="noreferrer"><Icon name="picture_as_pdf" size={18} /> PDF</a>
            {/* แชร์/ดาวน์โหลดเป็นไฟล์ — ทั้งพนักงานและลูกค้าที่เปิดใบอยู่ใช้ได้ */}
            <button className="btn sm" onClick={() => setShareOpen(true)}><Icon name="ios_share" size={18} /> แชร์ / ดาวน์โหลด</button>
            {isStaff && <a className="btn sm" href={exportUrl("xlsx")}><Icon name="table_view" size={18} /> Excel</a>}
            {isStaff && <a className="btn sm" href={exportUrl("csv")}><Icon name="download" size={18} /> CSV</a>}
            {isStaff && <button className="btn sm" onClick={() => openGoogleSheet(q.quotation_no, tk).then(setMsg).catch((e) => setMsg(errorMessage(e)))}><Icon name="grid_on" size={18} /> Google Sheets</button>}
            {isStaff && <button className="btn sm" disabled={busy !== null} onClick={() => send("email")}><Icon name="mail" size={18} /> ส่งอีเมล</button>}
            {isStaff && <button className="btn sm" disabled={busy !== null} onClick={() => send("sms")}><Icon name="sms" size={18} /> ส่ง SMS</button>}
            {isStaff && shareLink && <button className="btn sm" onClick={() => { navigator.clipboard?.writeText(shareLink); setMsg("คัดลอกลิงก์แล้ว: " + shareLink); }}><Icon name="link" size={18} /> คัดลอกลิงก์</button>}
            {isStaff && q.status === "issued" && <button className="btn sm" style={{ marginLeft: "auto", color: "var(--red)" }} disabled={busy !== null} onClick={cancel}>ยกเลิก + ออกใหม่</button>}
          </div>
          {msg && <div className="note ok small" style={{ marginTop: 8, wordBreak: "break-all" }}>{msg}</div>}
        </div>

        <aside className="cart-side">
          <div className="summary">
            <h3>สรุปยอด</h3>
            <div className="sum-row"><span>รวมสินค้า</span><b>{bahtWord(q.subtotal)}</b></div>
            {q.discounts.map((d, i) => (
              <div key={i} className="sum-row"><span>{d.title || d.code}</span><span className="green">−{bahtWord(d.amount)}</span></div>
            ))}
            <div className="sum-row"><span>ค่าขนส่ง{Number(q.install_fee) > 0 ? " + ติดตั้ง" : ""}{q.slot_date ? ` (${thDate(q.slot_date)} ${q.slot_period === "am" ? "เช้า" : "บ่าย"})` : ""}</span><b>{bahtWord(feeTotal)}</b></div>
            <div className="sum-total"><span>รวมสุทธิ (รวม VAT 7%)</span><b>{bahtWord(q.grand_total)}</b></div>
            <div className="tiny muted">VAT ที่รวมอยู่ {bahtWord(q.vat)}{cfg?.deposit_enabled ? ` · มัดจำ 20% = ${bahtWord(q.deposit_amount)}` : ""}</div>
            {q.sap_so_no && <div className="note ok" style={{ marginTop: 10 }}>SO {q.sap_so_no} · sync {q.sap_sync_status}</div>}
            {q.status === "issued" ? (
              <div className="col" style={{ marginTop: 12 }}>
                <Link to={payHref} className="btn primary lg block">{isStaff ? "ไปหน้าชำระเงิน" : "ชำระเงินทั้งจำนวน"}</Link>
                {!isStaff && cfg?.deposit_enabled && <Link to={payHref + (token ? "&" : "?") + "deposit=1"} className="btn block">จ่ายมัดจำ 20% ({bahtWord(q.deposit_amount)})</Link>}
                <p className="tiny muted" style={{ margin: 0 }}>{isStaff ? `QR PromptPay ที่แท็บเล็ต · ส่งลิงก์จ่ายเข้ามือถือ · บัตร/ผ่อนที่แคชเชียร์${cfg?.deposit_enabled ? " · มัดจำ 20%" : ""}` : "ชำระผ่าน QR PromptPay / บัตร / ผ่อน 0% · เมื่อจ่ายสำเร็จจะได้เลข SO ทันที"}</p>
              </div>
            ) : q.status === "paid" || q.status === "converted" ? (
              <div className="note ok" style={{ marginTop: 12 }}>{q.sap_so_no ? <>ชำระเงินแล้ว · คำสั่งซื้อ <b className="mono">SO {q.sap_so_no}</b></> : "ชำระเงินแล้ว · กำลังส่งคำสั่งซื้อเข้าระบบ SAP"}</div>
            ) : null}
          </div>
        </aside>
      </div>
      {shareOpen && <QuotationShare no={q.quotation_no} token={tk} onClose={() => setShareOpen(false)} />}
    </main>
  );
}
