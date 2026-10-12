import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import Icon from "../components/Icon";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import { bahtWord, thDate, thDateTime } from "../lib/format";
import type { Payment } from "../lib/types";

type Cand = {
  quotation_no: string; issued_at: string; valid_until: string; grand_total: string; discount_total: string;
  item_count: number; first_item: string; sales_name: string | null; sales_code: string | null; mine: boolean;
};
type Customer = { id: string; name: string; sap_customer_no: string | null; phone: string | null };
type Promo = { code: string; title: string; min: string; amount: string; expires: string; eligible: boolean; short_by: string };
type Bill = {
  bill_no: string; status: "open" | "paid" | "cancelled"; customer: Customer; promo_code: string | null; promo_title: string | null;
  subtotal: string; discount: string; grand_total: string; created_at: string; paid_at: string | null; pending_payment: string | null;
  attempts: { payment_no: string; method: string; status: string; amount: string; created_at: string; paid_at: string | null; failed_reason: string | null }[];
  items: { quotation_no: string; status: string; amount: string; discount_share: string; sales_name: string | null; sap_so_no: string | null }[];
};

const METHODS = [
  { id: "qr_promptpay", icon: "qr_code_2", label: "QR PromptPay" },
  { id: "card", icon: "credit_card", label: "บัตรเครดิต/เดบิต" },
  { id: "installment", icon: "calendar_month", label: "ผ่อน 0%" },
] as const;
const QS: Record<string, string> = { issued: "รอชำระ", paid: "ชำระแล้ว", converted: "สร้าง SO แล้ว", cancelled: "ยกเลิก" };

/** บิลรวม (Big Bill) — /sales/bigbill?q=QT1,QT2 (เลือกใบ) · /sales/bigbill/:no (บิลที่สร้างแล้ว/ผลการชำระ) */
export default function BigBillPage() {
  const { no } = useParams();
  return no ? <BillView no={no} /> : <BillBuilder />;
}

function BillBuilder() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const start = (params.get("q") || "").split(",").filter(Boolean);
  const [cust, setCust] = useState<Customer | null>(null);
  const [cands, setCands] = useState<Cand[] | null>(null);
  const [sel, setSel] = useState<string[]>(start);
  const [promos, setPromos] = useState<Promo[]>([]);
  const [code, setCode] = useState<string | null>(null);
  const [method, setMethod] = useState<string>("qr_promptpay");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [find, setFind] = useState("");

  useEffect(() => {
    if (!start[0]) return;
    apiGet<{ customer: Customer; quotations: Cand[] }>(`/sales/bigbill/candidates?quotation_no=${encodeURIComponent(start[0])}`)
      .then((r) => { setCust(r.customer); setCands(r.quotations); })
      .catch((e) => setErr(errorMessage(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const chosen = useMemo(() => (cands || []).filter((c) => sel.includes(c.quotation_no)), [cands, sel]);
  const subtotal = chosen.reduce((n, c) => n + Number(c.grand_total), 0);

  // โค้ดคิดจากยอดรวมที่เลือก — ยอดเปลี่ยน เช็คเงื่อนไขใหม่ · โค้ดที่เลือกไว้แต่ยอดไม่ถึงแล้ว ปลดออก
  useEffect(() => {
    apiGet<Promo[]>(`/sales/bigbill/promos?amount=${subtotal}`).then((ps) => {
      setPromos(ps);
      setCode((c) => (c && ps.find((p) => p.code === c)?.eligible ? c : null));
    }).catch(() => setPromos([]));
  }, [subtotal]);

  const promo = promos.find((p) => p.code === code) || null;
  const discount = promo ? Number(promo.amount) : 0;

  // ค้นจากเลขใบ ชื่อสินค้า หรือชื่อ/รหัสพนักงาน — ใบที่ติ๊กไว้ยังนับยอดแม้ค้นแล้วไม่โชว์
  const term = find.trim().toLowerCase();
  const shown = (cands || []).filter((c) => !term || [c.quotation_no, c.first_item, c.sales_name || "ออนไลน์", c.sales_code || "", c.mine ? "ของฉัน" : ""]
    .some((x) => x.toLowerCase().includes(term)));
  const hiddenPicked = chosen.filter((c) => !shown.includes(c)).length;
  const allShownPicked = shown.length > 0 && shown.every((c) => sel.includes(c.quotation_no));
  const pickShown = (on: boolean) => setSel((cur) => on
    ? [...new Set([...cur, ...shown.map((c) => c.quotation_no)])]
    : cur.filter((x) => !shown.some((c) => c.quotation_no === x)));

  const toggle = (q: string) => setSel((cur) => (cur.includes(q) ? cur.filter((x) => x !== q) : [...cur, q]));

  const payNow = async () => {
    setBusy(true);
    setErr(null);
    try {
      const bill = await apiPost<Bill>("/sales/bigbills", { quotation_nos: chosen.map((c) => c.quotation_no), promo_code: code });
      const pay = await apiPost<Payment>(`/sales/bigbills/${bill.bill_no}/pay`, { method });
      // gateway จำลอง = หน้าธนาคารจำลองของเรา · ของจริงพาออกไปหน้าธนาคาร
      if (pay.pay_url?.startsWith("http")) window.location.href = pay.pay_url;
      else nav(pay.pay_url || `/sales/bigbill/${bill.bill_no}`);
    } catch (e) {
      setErr(errorMessage(e));
      setBusy(false);
    }
  };

  if (!start[0]) return <main className="container sec"><div className="note">เลือกใบเสนอราคาจากแท็บ "ออก Quotation แล้ว" ก่อน — <Link to="/sales/presos">ไปที่ Preso ของฉัน</Link></div></main>;

  return (
    <main className="container sec bb">
      <Link to="/sales/presos" className="row small muted" style={{ marginBottom: 10 }}><Icon name="arrow_back" size={18} /> Preso ของฉัน</Link>
      <h1 style={{ margin: "0 0 4px" }}>ชำระรวม (Big Bill)</h1>
      <p className="small muted" style={{ margin: "0 0 14px" }}>รวมใบเสนอราคาที่รอชำระของลูกค้าคนเดียว จ่ายครั้งเดียว · แต่ละใบยังเป็น SO แยกใน SAP และนับยอดให้พนักงานที่ออกใบ</p>
      {err && <div className="note err" style={{ marginBottom: 10 }}>{err}</div>}

      <div className="bb-grid">
        <div>
          <section className="od-card">
            <h3><Icon name="person" size={18} /> ลูกค้า</h3>
            {cust ? <div><b>{cust.name}</b> <span className="muted small">· รหัส {cust.sap_customer_no || "-"}{cust.phone ? ` · ${cust.phone}` : ""}</span></div> : <div className="small muted">กำลังโหลด…</div>}
          </section>

          <section className="od-card" style={{ marginTop: 12 }}>
            <h3><Icon name="receipt_long" size={18} /> ใบเสนอราคาที่รอชำระ ({cands?.length ?? "…"})</h3>
            <div className="bb-find">
              <label className="bb-search">
                <Icon name="search" size={18} />
                <input value={find} onChange={(e) => setFind(e.target.value)} placeholder="ค้นหาเลขที่ใบ ชื่อสินค้า หรือพนักงาน" aria-label="ค้นหาใบเสนอราคา" />
                {find && <button className="icon-btn sm" onClick={() => setFind("")} aria-label="ล้างคำค้น"><Icon name="close" size={16} /></button>}
              </label>
              <label className="bb-all">
                <input type="checkbox" checked={allShownPicked} disabled={shown.length === 0} onChange={(e) => pickShown(e.target.checked)} />
                เลือกทั้งหมด{term ? "ที่ค้นเจอ" : ""} ({shown.length})
              </label>
            </div>
            {hiddenPicked > 0 && <div className="tiny muted" style={{ marginBottom: 6 }}>เลือกไว้อีก {hiddenPicked} ใบที่ไม่ตรงคำค้น — ยังนับอยู่ในยอดรวม</div>}
            <div className="tbl-wrap">
              <table className="tbl bb-tbl">
                <thead><tr><th></th><th>เลขที่</th><th>วันที่</th><th>สินค้า</th><th>พนักงาน</th><th className="r">ยอดสุทธิ</th></tr></thead>
                <tbody>
                  {shown.map((c) => (
                    <tr key={c.quotation_no} className={sel.includes(c.quotation_no) ? "picked" : ""} onClick={() => toggle(c.quotation_no)}>
                      <td><input type="checkbox" checked={sel.includes(c.quotation_no)} onChange={() => toggle(c.quotation_no)} onClick={(e) => e.stopPropagation()} aria-label={`เลือก ${c.quotation_no}`} /></td>
                      <td><b className="mono">{c.quotation_no}</b><div className="tiny muted">ยืนราคาถึง {thDate(c.valid_until, true)}</div></td>
                      <td className="small">{thDate(c.issued_at, true)}</td>
                      <td className="small">{c.first_item}{c.item_count > 1 ? ` +${c.item_count - 1}` : ""}</td>
                      <td className="small">{c.mine ? <b>ของฉัน</b> : <>{c.sales_name || "ออนไลน์"}{c.sales_code ? <span className="muted"> ({c.sales_code})</span> : null}</>}</td>
                      <td className="r"><b>{bahtWord(c.grand_total)}</b></td>
                    </tr>
                  ))}
                  {cands && cands.length === 0 && <tr><td colSpan={6} className="muted">ไม่มีใบรอชำระ</td></tr>}
                  {cands && cands.length > 0 && shown.length === 0 && <tr><td colSpan={6} className="muted">ไม่พบใบที่ตรงกับ "{find}"</td></tr>}
                </tbody>
              </table>
            </div>
          </section>

          <section className="od-card" style={{ marginTop: 12 }}>
            <h3><Icon name="sell" size={18} /> โค้ดส่วนลดระดับบิล <span className="chip light" style={{ marginLeft: 6 }}>DEMO</span></h3>
            <p className="tiny muted" style={{ margin: "-4px 0 8px" }}>คิดจากยอดรวมทุกใบที่เลือก · ใช้ได้ครั้งละ 1 โค้ด</p>
            <div className="bb-promos">
              {promos.map((p) => (
                <label key={p.code} className={"bb-promo" + (p.eligible ? "" : " off") + (code === p.code ? " on" : "")}>
                  <input type="radio" name="promo" disabled={!p.eligible} checked={code === p.code} onChange={() => setCode(p.code)} />
                  <span className="grow">
                    <b>{p.code}</b> · {p.title}
                    <small>{p.eligible ? `หมดอายุ ${thDate(p.expires, true)}` : `ขาดอีก ${bahtWord(p.short_by)} ถึงใช้ได้`}</small>
                  </span>
                  <b className="green">−{bahtWord(p.amount)}</b>
                </label>
              ))}
              {code && <button className="link-btn small" onClick={() => setCode(null)}>ไม่ใช้โค้ด</button>}
            </div>
          </section>
        </div>

        <aside className="od-card bb-side">
          <h3>รายละเอียดการชำระเงิน</h3>
          <div className="od-sum" style={{ borderTop: 0, marginTop: 0, paddingTop: 0 }}>
            <div><span>จำนวนใบ</span><span>{chosen.length} ใบ</span></div>
            <div><span>ยอดรวม</span><span>{bahtWord(subtotal)}</span></div>
            <div><span>ส่วนลดบิล{promo ? ` (${promo.code})` : ""}</span><span className={discount ? "green" : ""}>{discount ? `−${bahtWord(discount)}` : "0"}</span></div>
            <div className="od-total"><span>ยอดชำระ</span><b>{bahtWord(Math.max(0, subtotal - discount))}</b></div>
          </div>
          <div className="bb-methods">
            {METHODS.map((m) => (
              <label key={m.id} className={"bb-method" + (method === m.id ? " on" : "")}>
                <input type="radio" name="method" checked={method === m.id} onChange={() => setMethod(m.id)} />
                <Icon name={m.icon} size={18} /> {m.label}
              </label>
            ))}
          </div>
          <button className="btn primary block lg" disabled={busy || chosen.length === 0} onClick={payNow}>
            {busy ? "กำลังสร้างรายการชำระ…" : `ชำระรวม ${chosen.length} ใบ`}
          </button>
          <p className="tiny muted" style={{ marginTop: 8 }}>ไม่รับเงินสด · ชำระผ่าน QR / บัตร / ผ่อน ในรายการเดียว · จ่ายสำเร็จทุกใบเป็น "ชำระแล้ว" พร้อมกัน</p>
        </aside>
      </div>
    </main>
  );
}

const ATTEMPT_TXT: Record<string, string> = { pending: "รอชำระ", paid: "ชำระสำเร็จ", failed: "ชำระไม่สำเร็จ", cancelled: "ยกเลิกการชำระ", expired: "หมดเวลาชำระ" };
const METHOD_TXT: Record<string, string> = { qr_promptpay: "QR PromptPay", card: "บัตรเครดิต/เดบิต", installment: "ผ่อน 0%" };

function BillView({ no }: { no: string }) {
  const nav = useNavigate();
  const [b, setB] = useState<Bill | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [method, setMethod] = useState<string>("qr_promptpay");
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => { apiGet<Bill>(`/sales/bigbills/${no}`).then(setB).catch((e) => setErr(errorMessage(e))); }, [no]);

  if (!b) return <main className="container sec">{err ? <div className="note err">{err}</div> : <div className="ph" style={{ height: 200 }}>กำลังโหลด…</div>}</main>;
  const paid = b.status === "paid";
  const last = b.attempts[0];
  // หัวหน้า: บิลจ่ายแล้ว/ยกเลิก หรือยังเปิดอยู่ + ผลการกดชำระรอบล่าสุด
  const head = paid ? { tone: "green", title: "ชำระรวมสำเร็จ", icon: "task_alt" }
    : b.status === "cancelled" ? { tone: "red", title: "บิลนี้ถูกยกเลิก", icon: "cancel" }
    : b.pending_payment ? { tone: "amber", title: "รอชำระ — เปิดหน้าชำระเงินค้างอยู่", icon: "hourglass_top" }
    : last?.status === "cancelled" ? { tone: "amber", title: "ยกเลิกการชำระ — บิลยังเปิดอยู่ ชำระใหม่ได้", icon: "undo" }
    : last?.status === "failed" ? { tone: "red", title: "ชำระไม่สำเร็จ — ลองใหม่หรือเปลี่ยนช่องทาง", icon: "error" }
    : last?.status === "expired" ? { tone: "amber", title: "หมดเวลาชำระ — ชำระใหม่ได้", icon: "timer_off" }
    : { tone: "amber", title: "ยังไม่ได้ชำระ", icon: "receipt_long" };

  const payAgain = async () => {
    setBusy("pay");
    setErr(null);
    try {
      const pay = await apiPost<Payment>(`/sales/bigbills/${b.bill_no}/pay`, { method });
      if (pay.pay_url?.startsWith("http")) window.location.href = pay.pay_url;
      else nav(pay.pay_url || `/pay/${pay.payment_no}/bank`);
    } catch (e) {
      setErr(errorMessage(e));
      setBusy(null);
    }
  };
  const cancelBill = async () => {
    if (!confirm(`ยกเลิกบิลรวม ${b.bill_no}? ใบในบิลจะกลับไปเป็นใบรอชำระปกติ (จ่ายแยกหรือรวมบิลใหม่ได้)`)) return;
    setBusy("cancel");
    setErr(null);
    try {
      setB(await apiPost<Bill>(`/sales/bigbills/${b.bill_no}/cancel`, {}));
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <main className="container sec od">
      <Link to="/sales/presos" className="row small muted od-back"><Icon name="arrow_back" size={18} /> Preso ของฉัน</Link>
      <section className={"od-banner " + head.tone}>
        <div>
          <b>{head.title}</b>
          <span>บิลรวม {b.bill_no} · {b.customer.name}{paid && b.paid_at ? ` · ชำระเมื่อ ${thDateTime(b.paid_at)}` : ""}
            {!paid && last?.status === "failed" && last.failed_reason ? ` · ${last.failed_reason}` : ""}</span>
        </div>
        <Icon name={head.icon} size={34} />
      </section>
      {err && <div className="note err" style={{ marginTop: 10 }}>{err}</div>}

      {b.status === "open" && (
        <section className="od-card bb-again" style={{ marginTop: 12 }}>
          {b.pending_payment ? (
            <>
              <span className="grow small">มีหน้าชำระเงินที่เปิดค้างไว้ ({b.pending_payment})</span>
              <button className="btn primary" onClick={() => nav(`/pay/${b.pending_payment}/bank`)}>ไปหน้าชำระเงิน</button>
            </>
          ) : (
            <>
              <div className="bb-methods">
                {METHODS.map((m) => (
                  <label key={m.id} className={"bb-method" + (method === m.id ? " on" : "")}>
                    <input type="radio" name="method2" checked={method === m.id} onChange={() => setMethod(m.id)} />
                    <Icon name={m.icon} size={18} /> {m.label}
                  </label>
                ))}
              </div>
              <button className="btn primary" disabled={busy !== null} onClick={payAgain}>{busy === "pay" ? "กำลังเปิดหน้าชำระ…" : `ชำระ ${bahtWord(b.grand_total)}`}</button>
            </>
          )}
          <button className="link-btn small" disabled={busy !== null} onClick={cancelBill} style={{ color: "var(--red)" }}>ยกเลิกบิลรวม</button>
        </section>
      )}

      <section className="od-card" style={{ marginTop: 12 }}>
        <h3><Icon name="receipt_long" size={18} /> ใบในบิลนี้ ({b.items.length})</h3>
        <table className="tbl">
          <thead><tr><th>เลขที่</th><th>พนักงาน</th><th>สถานะ</th><th>เลข SO</th><th className="r">ยอด</th><th className="r">ส่วนลดบิล</th></tr></thead>
          <tbody>
            {b.items.map((i) => (
              <tr key={i.quotation_no}>
                <td><Link to={`/sales/quotations/${i.quotation_no}`} className="mono strong">{i.quotation_no}</Link></td>
                <td className="small">{i.sales_name || "ออนไลน์"}</td>
                <td className="small">{QS[i.status] || i.status}</td>
                <td className="mono small">{i.sap_so_no || "-"}</td>
                <td className="r">{bahtWord(i.amount)}</td>
                <td className="r green">{Number(i.discount_share) ? `−${bahtWord(i.discount_share)}` : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="od-sum">
          <div><span>ยอดรวม</span><span>{bahtWord(b.subtotal)}</span></div>
          <div><span>ส่วนลดบิล{b.promo_code ? ` (${b.promo_code})` : ""}</span><span className="green">{Number(b.discount) ? `−${bahtWord(b.discount)}` : "0"}</span></div>
          <div className="od-total"><span>ยอดชำระ</span><b>{bahtWord(b.grand_total)}</b></div>
        </div>
      </section>
      {b.attempts.length > 0 && (
        <section className="od-card" style={{ marginTop: 12 }}>
          <h3><Icon name="history" size={18} /> ประวัติการชำระ ({b.attempts.length})</h3>
          <table className="tbl">
            <thead><tr><th>เวลา</th><th>รายการ</th><th>ช่องทาง</th><th>ผล</th><th className="r">ยอด</th></tr></thead>
            <tbody>
              {b.attempts.map((x) => (
                <tr key={x.payment_no}>
                  <td className="small">{thDateTime(x.created_at)}</td>
                  <td className="mono small">{x.payment_no}</td>
                  <td className="small">{METHOD_TXT[x.method] || x.method}</td>
                  <td className="small"><span className={"bb-att " + x.status}>{ATTEMPT_TXT[x.status] || x.status}</span>{x.failed_reason ? <div className="tiny muted">{x.failed_reason}</div> : null}</td>
                  <td className="r small">{bahtWord(x.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </main>
  );
}
