import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import Icon from "../components/Icon";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { bahtWord, thDate } from "../lib/format";
import type { Payment, PaymentMethod, Quotation } from "../lib/types";

const METHODS: { id: PaymentMethod; icon: string; label: string; note: string }[] = [
  { id: "qr_promptpay", icon: "qr_code_2", label: "QR PromptPay", note: "สแกนจ่ายจากแอปธนาคาร" },
  { id: "card", icon: "credit_card", label: "บัตรเครดิต/เดบิต", note: "Visa · Mastercard · JCB" },
  { id: "installment", icon: "calendar_month", label: "ผ่อน 0% 10 เดือน", note: "บัตรเครดิตที่ร่วมรายการ" },
  { id: "link", icon: "link", label: "ลิงก์จ่ายเข้ามือถือ", note: "ส่งให้ลูกค้าจ่ายเองทีหลัง" },
];

/** ตารางจุดจำลอง QR จาก payload (mock — ของจริงใช้ QR library/ภาพจาก PSP) */
function QrArt({ payload }: { payload: string }) {
  const cells: boolean[] = [];
  let h = 7;
  for (let i = 0; i < 625; i++) {
    h = (h * 31 + payload.charCodeAt(i % payload.length)) % 100003;
    cells.push(h % 2 === 0);
  }
  return (
    <div className="qr-art" aria-label="QR สำหรับสแกนจ่าย">
      {cells.map((on, i) => (
        <i key={i} className={on ? "on" : ""} />
      ))}
    </div>
  );
}

/** C3 · หน้าชำระเงิน — ลูกค้าเปิดจากลิงก์ (?t=) หรือเซลล์กดที่แท็บเล็ต (เซลล์ไม่รับเงินสด) */
export default function PayPage() {
  const { no = "" } = useParams();
  const [params] = useSearchParams();
  const token = params.get("t");
  const wantDeposit = params.get("deposit") === "1";
  const auth = useAuth();
  const [q, setQ] = useState<Quotation | null>(null);
  const [pay, setPay] = useState<Payment | null>(null);
  const [method, setMethod] = useState<PaymentMethod>("qr_promptpay");
  const [kind, setKind] = useState<"full" | "deposit">(wantDeposit ? "deposit" : "full");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | null>(null);
  const qs = token ? `?t=${encodeURIComponent(token)}` : "";

  useEffect(() => {
    if (auth.ready) apiGet<Quotation>(`/quotations/${no}${qs}`).then(setQ).catch((e) => setErr(errorMessage(e)));
  }, [no, qs, auth.ready, auth.user?.id]);

  // รอ webhook จาก provider — poll จนกว่าจะจ่ายสำเร็จหรือหมดอายุ
  const poll = useCallback((paymentNo: string) => {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = window.setInterval(async () => {
      try {
        const p = await apiGet<Payment>(`/payments/${paymentNo}${qs}`);
        setPay(p);
        if (p.status !== "pending" && timer.current) window.clearInterval(timer.current);
      } catch {
        /* เดี๋ยวรอบหน้าลองใหม่ */
      }
    }, 2500);
  }, [qs]);
  useEffect(() => () => { if (timer.current) window.clearInterval(timer.current); }, []);

  const start = async () => {
    setBusy(true);
    setErr(null);
    try {
      const p = await apiPost<Payment>(`/quotations/${no}/payment-intent${qs}`, { method, kind });
      setPay(p);
      poll(p.payment_no);
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const mockPaid = async () => {
    if (!pay) return;
    setBusy(true);
    try {
      setPay(await apiPost<Payment>(`/payments/${pay.payment_no}/mock-confirm${qs}`));
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (err && !q) return <main className="container sec"><div className="note err">{err}</div></main>;
  if (!q) return <main className="container sec"><div className="ph" style={{ height: 200 }}>กำลังโหลด…</div></main>;

  const amount = kind === "deposit" ? q.deposit_amount : q.grand_total;
  const done = pay?.status === "paid";
  const soNo = pay?.sap_so_no || q.sap_so_no;

  if (done) {
    return (
      <main className="container sec">
        <div className="card pay-done">
          <div className="pay-tick"><Icon name="check_circle" size={44} /></div>
          <h1>ชำระเงินสำเร็จ</h1>
          <p className="muted">{q.quotation_no} · {pay?.kind === "deposit" ? "มัดจำ 20%" : "เต็มจำนวน"} {bahtWord(pay?.amount)}</p>
          {soNo ? (
            <div className="note ok">เลขที่คำสั่งซื้อ (SO) <b className="mono">{soNo}</b> — ส่งเข้าระบบ SAP แล้ว</div>
          ) : (
            <div className="note warn">รับเงินเรียบร้อย · กำลังส่งคำสั่งซื้อเข้าระบบ SAP (ระบบจะลองใหม่อัตโนมัติ แล้วแจ้งเลข SO ให้ทางอีเมล)</div>
          )}
          {q.slot_date && <p className="small">นัดส่ง <b>{thDate(q.slot_date, true)}</b> {q.slot_period === "am" ? "รอบเช้า (09:00–12:00)" : "รอบบ่าย (13:00–17:00)"} · {q.ship_address} {q.ship_postcode}</p>}
          <div className="row wrap" style={{ gap: 8, marginTop: 12 }}>
            <Link to={`/q/${q.quotation_no}${qs}`} className="btn">ดูใบเสนอราคา</Link>
            <Link to="/" className="btn primary">กลับหน้าแรก</Link>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="container sec">
      <div className="cart-grid">
        <div className="cart-main">
          <h1 className="cart-title">ชำระเงิน · {q.quotation_no}</h1>
          {err && <div className="note err">{err}</div>}
          {pay?.status === "failed" && <div className="note err">ชำระเงินไม่สำเร็จ กรุณาลองใหม่หรือเปลี่ยนช่องทาง</div>}
          {pay?.status === "expired" && <div className="note warn">รายการหมดอายุ (15 นาที) กรุณากดสร้างรายการใหม่</div>}

          <div className="seg" style={{ maxWidth: 420 }}>
            <button className={"seg-btn" + (kind === "full" ? " on" : "")} onClick={() => { setKind("full"); setPay(null); }}>เต็มจำนวน {bahtWord(q.grand_total)}</button>
            <button className={"seg-btn" + (kind === "deposit" ? " on" : "")} onClick={() => { setKind("deposit"); setPay(null); }}>มัดจำ 20% {bahtWord(q.deposit_amount)}</button>
          </div>

          <div className="pay-methods">
            {METHODS.map((m) => (
              <button key={m.id} className={"pay-method" + (method === m.id ? " on" : "")} onClick={() => { setMethod(m.id); setPay(null); }}>
                <Icon name={m.icon} size={22} />
                <div><b>{m.label}</b><div className="small muted">{m.note}</div></div>
              </button>
            ))}
          </div>
          <p className="tiny muted">ระบบไม่รับเงินสด — พนักงานขายรับเงินเองไม่ได้ ลูกค้าชำระผ่านช่องทางข้างต้นหรือที่แคชเชียร์เท่านั้น</p>

          {pay?.status === "pending" && (
            <div className="card flat pay-intent">
              {pay.qr_payload ? (
                <>
                  <QrArt payload={pay.qr_payload} />
                  <div><b>สแกนจ่าย {bahtWord(pay.amount)}</b><div className="small muted">{pay.payment_no} · หมดอายุใน 15 นาที</div><div className="small">กำลังรอผลจากธนาคาร…</div></div>
                </>
              ) : (
                <div><b>ส่งลิงก์ให้ลูกค้าชำระ {bahtWord(pay.amount)}</b><div className="small muted mono" style={{ wordBreak: "break-all" }}>{location.origin}{pay.pay_url}</div><div className="small">กำลังรอผลการชำระเงิน…</div></div>
              )}
              <button className="btn sm" disabled={busy} onClick={mockPaid} title="โหมด dev: จำลองว่า provider ยิง webhook สำเร็จ">จำลองจ่ายสำเร็จ (dev)</button>
            </div>
          )}

          {pay?.status !== "pending" && (
            <button className="btn primary lg" disabled={busy} onClick={start}>{busy ? "กำลังสร้างรายการ…" : `ชำระ ${bahtWord(amount)}`}</button>
          )}
        </div>

        <aside className="cart-side">
          <div className="summary">
            <h3>สรุปคำสั่งซื้อ</h3>
            {q.lines.map((l) => (
              <div key={l.matnr + l.supply_mode} className="sum-row"><span>{l.name} ×{l.qty}</span><b>{bahtWord(l.line_total)}</b></div>
            ))}
            {q.discounts.map((d, i) => (
              <div key={i} className="sum-row"><span>{d.title || d.code}</span><span className="green">−{bahtWord(d.amount)}</span></div>
            ))}
            <div className="sum-row"><span>ค่าขนส่ง{Number(q.install_fee) > 0 ? " + ติดตั้ง" : ""}</span><b>{bahtWord(Number(q.shipping_fee) + Number(q.install_fee) - Number(q.shipping_discount))}</b></div>
            <div className="sum-total"><span>รวมสุทธิ (รวม VAT 7%)</span><b>{bahtWord(q.grand_total)}</b></div>
            <div className="tiny muted">ยืนราคาถึง {thDate(q.valid_until, true)} · ชำระมัดจำ 20% ({bahtWord(q.deposit_amount)}) แล้วจ่ายส่วนที่เหลือวันส่งได้</div>
          </div>
        </aside>
      </div>
    </main>
  );
}
