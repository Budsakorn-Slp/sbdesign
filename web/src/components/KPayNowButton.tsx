import { useEffect, useRef, useState } from "react";
import { apiPost, errorMessage } from "../lib/api";
import type { PublicConfig } from "../lib/publicConfig";

/** ปุ่ม Pay Now ของ K-Payment Gateway (Embedded UI / Smart Pay)
 *
 *  ลำดับตามเอกสารธนาคาร:
 *    1 กด Pay Now  ->  kpayment.js เปิดหน้าจอให้กรอกรายละเอียดบัตร
 *    2 ลูกค้ายืนยัน  ->  ธนาคารเก็บข้อมูลบัตรเองแล้วคืน token กลับมาให้เรา
 *    3 เราส่ง token ไปให้หลังบ้านเรียก Create Charge API (source_type = "card")
 *    4 ธนาคารตอบ Dynamic URL มาใน redirect_url -> พาลูกค้าไปยืนยันตัวตนต่อ
 *
 *  ข้อมูลบัตรไม่เคยผ่านมือเรา — อยู่ในหน้าจอของธนาคารทั้งหมด เราได้แค่ token
 *  (นี่คือเหตุผลที่ต้องใช้ปุ่มของเขา ไม่ใช่ทำฟอร์มกรอกบัตรเอง)
 *
 *  ยังไม่ได้คีย์จากธนาคาร = ไม่แสดงปุ่ม · ดีกว่าโชว์ปุ่มที่กดแล้วไม่มีอะไรเกิดขึ้น
 */
type Props = { paymentNo: string; amount: string; cfg: PublicConfig | null; token?: string | null };

declare global {
  interface Window {
    KPayment?: {
      create?: (opts: Record<string, unknown>) => void;
      setApiKey?: (key: string) => void;
    };
  }
}

export default function KPayNowButton({ paymentNo, amount, cfg, token }: Props) {
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement | null>(null);

  const enabled = cfg?.payment_provider === "kbank" && !!cfg?.kbank_public_key && !!cfg?.kbank_script_url;

  // โหลด kpayment.js จากธนาคาร — โหลดครั้งเดียวต่อการเปิดเว็บ ถึงจะมีหลายหน้าก็ใช้ตัวเดิม
  useEffect(() => {
    if (!enabled) return;
    const src = cfg!.kbank_script_url;
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${src}"]`);
    if (existing) { setReady(true); return; }
    const el = document.createElement("script");
    el.src = src;
    el.async = true;
    el.onload = () => setReady(true);
    el.onerror = () => setErr("โหลดสคริปต์ของธนาคารไม่สำเร็จ");
    document.head.appendChild(el);
  }, [enabled, cfg]);

  // ธนาคารคืน token มาเป็นค่าใน form ที่เขาสร้างให้ (ชื่อฟิลด์ตามสเปกของ kpayment.js)
  // เมื่อได้ token แล้วค่อยส่งต่อให้หลังบ้านเรียก Create Charge API
  const chargeWithToken = async (tok: string) => {
    setBusy(true);
    setErr(null);
    try {
      const r = await apiPost<{ redirect_url: string }>(`/payments/${paymentNo}/kbank/charge`, { token: tok });
      window.location.href = r.redirect_url;   // Dynamic URL ของธนาคาร
    } catch (e) {
      setErr(errorMessage(e));
      setBusy(false);
    }
  };

  useEffect(() => {
    if (token) void chargeWithToken(token);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  if (!enabled) return null;

  return (
    <div className="kpay">
      {/* ปุ่มจริงถูกสร้างโดย kpayment.js ภายใน form นี้ — ค่าที่ใส่ตรงนี้คือสิ่งที่ธนาคารอ่าน
          ชื่อ attribute ต้องตรงกับสเปกของธนาคาร ตรวจกับเอกสารอีกรอบก่อนใช้จริง */}
      <form ref={formRef} id="kpayment-form" method="POST" action={`/payments/${paymentNo}/kbank/charge`}>
        <script
          type="text/javascript"
          data-apikey={cfg!.kbank_public_key}
          data-amount={amount}
          data-currency="THB"
          data-order-id={paymentNo}
          data-name="SB Design Square"
          data-payment-methods="card"
        />
      </form>
      {!ready && <div className="small muted">กำลังเตรียมหน้าชำระเงินของธนาคาร…</div>}
      {busy && <div className="small muted">กำลังส่งข้อมูลไปที่ธนาคาร…</div>}
      {err && <div className="note err small">{err}</div>}
    </div>
  );
}
