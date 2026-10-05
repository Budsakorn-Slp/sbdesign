import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import Icon from "../components/Icon";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import { usePublicConfig } from "../lib/publicConfig";
import { useAuth } from "../lib/auth";
import { bahtWord, thDate } from "../lib/format";
import type { Payment, PaymentMethod, Quotation } from "../lib/types";

const METHODS: { id: PaymentMethod; icon: string; label: string; note: string }[] = [
  { id: "qr_promptpay", icon: "qr_code_2", label: "QR PromptPay", note: "สแกนจ่ายจากแอปธนาคาร" },
  { id: "card", icon: "credit_card", label: "บัตรเครดิต/เดบิต", note: "Visa · Mastercard · JCB" },
  { id: "installment", icon: "calendar_month", label: "ผ่อน 0% 10 เดือน", note: "บัตรเครดิตที่ร่วมรายการ" },
];

export default function PayPage() {
  const { no = "" } = useParams();
  const [params] = useSearchParams();
  const token = params.get("t");
  const cfg = usePublicConfig();
  const nav = useNavigate();
  // ลิงก์เก่าที่ส่งให้ลูกค้าไปแล้วยังมี ?deposit=1 ติดอยู่ — ถ้าปิดรับมัดจำแล้วต้องไม่ยอมตาม
  // ไม่งั้นลูกค้าเปิดลิงก์เดิมมาเจอยอดมัดจำ กดจ่ายแล้วหลังบ้านตีกลับ งงทั้งคู่
  const wantDeposit = params.get("deposit") === "1" && cfg?.deposit_enabled === true;
  const auth = useAuth();
  const [q, setQ] = useState<Quotation | null>(null);
  const [method, setMethod] = useState<PaymentMethod>("qr_promptpay");
  const [kind, setKind] = useState<"full" | "deposit">("full");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const qs = token ? `?t=${encodeURIComponent(token)}` : "";

  useEffect(() => {
    if (wantDeposit) setKind("deposit");
  }, [wantDeposit]);

  useEffect(() => {
    if (auth.ready) apiGet<Quotation>(`/quotations/${no}${qs}`).then(setQ).catch((e) => setErr(errorMessage(e)));
  }, [no, qs, auth.ready, auth.user?.id]);

  // หน้านี้จบหน้าที่ตรงที่พาออกไปหน้าธนาคาร ผลการจ่ายไปรออ่านที่ /pay/{no}/result
  // ไม่ต้อง poll ค้างไว้ที่นี่อีก — ของเดิม poll ทุก 2.5 วินาทีไปเรื่อยๆ ขณะเปิดหน้าทิ้งไว้
  const start = async () => {
    setBusy(true);
    setErr(null);
    try {
      const p = await apiPost<Payment>(`/quotations/${no}/payment-intent${qs}`, { method, kind });
      // ของจริงลูกค้าจะถูกส่งออกไปที่เว็บธนาคาร — จำลองด้วยหน้า /pay/{no}/bank ของเราเอง
      nav(`/pay/${p.payment_no}/bank${qs}`);
    } catch (e) {
      setErr(errorMessage(e));
      setBusy(false);
    }
  };

  if (err && !q) return <main className="container sec"><div className="note err">{err}</div></main>;
  if (!q) return <main className="container sec"><div className="ph" style={{ height: 200 }}>กำลังโหลด…</div></main>;

  const amount = kind === "deposit" ? q.deposit_amount : q.grand_total;
  return (
    <main className="container sec">
      <h1 className="cart-title">ชำระเงิน · {q.quotation_no}</h1>
      {err && <div className="note err">{err}</div>}
      {/* สรุปคำสั่งซื้ออยู่ซ้าย ช่องทางจ่ายอยู่ขวา — คนอ่านว่าจ่ายอะไรก่อน แล้วค่อยเลือกวิธีจ่าย */}
      <div className="pay-grid">
        <section className="pay-summary">
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
            <div className="tiny muted">
              ยืนราคาถึง {thDate(q.valid_until, true)}
              {cfg?.deposit_enabled && ` · ชำระมัดจำ 20% (${bahtWord(q.deposit_amount)}) แล้วจ่ายส่วนที่เหลือวันส่งได้`}
            </div>
          </div>
        </section>

        <section className="pay-pick">
          <h3>เลือกช่องทางชำระเงิน</h3>
          {cfg?.deposit_enabled && (
            <div className="seg">
              <button className={"seg-btn" + (kind === "full" ? " on" : "")} onClick={() => setKind("full")}>เต็มจำนวน {bahtWord(q.grand_total)}</button>
              <button className={"seg-btn" + (kind === "deposit" ? " on" : "")} onClick={() => setKind("deposit")}>มัดจำ 20% {bahtWord(q.deposit_amount)}</button>
            </div>
          )}

          <div className="pay-methods">
            {METHODS.map((m) => (
              <button key={m.id} className={"pay-method" + (method === m.id ? " on" : "")} onClick={() => setMethod(m.id)}>
                <Icon name={m.icon} size={22} />
                <div><b>{m.label}</b><div className="small muted">{m.note}</div></div>
                <Icon name={method === m.id ? "radio_button_checked" : "radio_button_unchecked"} size={18} />
              </button>
            ))}
          </div>

          <button className="btn primary lg block" disabled={busy} onClick={start}>
            {busy ? "กำลังพาไปหน้าธนาคาร…" : `ชำระ ${bahtWord(amount)}`}
          </button>
          <p className="tiny muted" style={{ marginTop: 8 }}>
            <Icon name="lock" size={13} /> ระบบจะพาไปหน้าชำระเงินของธนาคารเพื่อยืนยันรายการ
          </p>
        </section>
      </div>
    </main>
  );
}
