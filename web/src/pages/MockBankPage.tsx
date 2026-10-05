import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import Icon from "../components/Icon";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import { bahtWord } from "../lib/format";
import type { Payment } from "../lib/types";

/** หน้าธนาคารจำลอง (mock KBank) — ของจริงลูกค้าจะถูกส่งออกไปที่เว็บของธนาคาร
 *
 *  ทำไมต้องมีหน้าจำลอง: เส้นทาง "จ่ายไม่สำเร็จ" กับ "ยกเลิก" คือเส้นที่คนลืมทดสอบ
 *  แล้วไปเจอหน้างานว่าเว็บค้างอยู่ที่ "กำลังรอผล" ตลอดกาล · มีหน้านี้แล้วกดลองได้ทั้งสามทาง
 *
 *  หน้าตาเลียนแบบหน้าธนาคารพอให้รู้ว่า "ออกจากเว็บเราไปแล้ว" แต่ติดป้ายว่าเป็นของจำลอง
 *  ไว้ชัดเจน จะได้ไม่มีใครเข้าใจผิดว่าต่อธนาคารจริงแล้ว
 */
export default function MockBankPage() {
  const { no = "" } = useParams();
  const [params] = useSearchParams();
  const token = params.get("t");
  const qs = token ? `?t=${encodeURIComponent(token)}` : "";
  const nav = useNavigate();

  const [pay, setPay] = useState<Payment | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [left, setLeft] = useState(15 * 60);

  useEffect(() => {
    apiGet<Payment>(`/payments/${no}${qs}`).then(setPay).catch((e) => setErr(errorMessage(e)));
  }, [no, qs]);

  // นับถอยหลังให้เหมือนหน้าธนาคารจริงที่มีเวลาจำกัด — หมดเวลาก็แค่หยุดนับ
  // ไม่ตัดสินใจแทนผู้ใช้ เพราะฝั่งหลังบ้านมีเวลาหมดอายุของตัวเองอยู่แล้ว
  useEffect(() => {
    if (left <= 0) return;
    const id = window.setTimeout(() => setLeft((n) => n - 1), 1000);
    return () => window.clearTimeout(id);
  }, [left]);

  const finish = async (outcome: "paid" | "failed" | "cancelled") => {
    setBusy(outcome);
    setErr(null);
    try {
      await apiPost<Payment>(`/payments/${no}/mock-confirm${qs ? qs + "&" : "?"}outcome=${outcome}`, {});
      // ส่งเลขรายการไปด้วยเพื่อให้หน้าผลไปถามสถานะจริงจากหลังบ้าน ไม่ใช่เชื่อค่าใน URL
      const sep = qs ? "&" : "?";
      nav(`/pay/${pay?.quotation_no || ""}/result${qs}${sep}p=${encodeURIComponent(no)}`, { replace: true });
    } catch (e) {
      setErr(errorMessage(e));
      setBusy(null);
    }
  };

  if (err && !pay) return <main className="container sec"><div className="note err">{err}</div></main>;
  if (!pay) return <main className="container sec"><div className="ph" style={{ height: 220 }}>กำลังเชื่อมต่อธนาคาร…</div></main>;

  const mm = String(Math.floor(Math.max(0, left) / 60)).padStart(2, "0");
  const ss = String(Math.max(0, left) % 60).padStart(2, "0");

  return (
    <main className="container sec">
      <div className="bankpay">
        <div className="bankpay-head">
          <div className="bankpay-logo">K</div>
          <div>
            <b>KBank Payment Gateway</b>
            <div className="small muted">ชำระเงินออนไลน์ · ปลอดภัยด้วยการเข้ารหัส</div>
          </div>
          <span className="bankpay-mock">จำลอง</span>
        </div>

        <div className="bankpay-body">
          <div className="bankpay-amt">
            <span className="small muted">ยอดที่ต้องชำระ</span>
            <b>{bahtWord(pay.amount)}</b>
          </div>
          <dl className="bankpay-kv">
            <dt>ร้านค้า</dt><dd>SB Design Square</dd>
            <dt>เลขที่รายการ</dt><dd className="mono">{pay.payment_no}</dd>
            <dt>อ้างอิงใบเสนอราคา</dt><dd className="mono">{pay.quotation_no}</dd>
            <dt>ช่องทาง</dt><dd>{METHOD_LABEL[pay.method] || pay.method}</dd>
            <dt>เวลาคงเหลือ</dt><dd className={left <= 60 ? "red" : ""}>{mm}:{ss} นาที</dd>
          </dl>

          {err && <div className="note err">{err}</div>}

          <div className="bankpay-actions">
            <button className="btn primary lg block" disabled={!!busy} onClick={() => finish("paid")}>
              {busy === "paid" ? "กำลังตัดเงิน…" : "ยืนยันการชำระเงิน"}
            </button>
            {/* สองปุ่มนี้คือเหตุผลที่หน้านี้มีอยู่ — ไม่ใช่ของตกแต่ง */}
            <button className="btn block" disabled={!!busy} onClick={() => finish("failed")}>
              {busy === "failed" ? "กำลังดำเนินการ…" : "จำลองกรณีธนาคารปฏิเสธ"}
            </button>
            <button className="link-btn" disabled={!!busy} onClick={() => finish("cancelled")}>
              {busy === "cancelled" ? "กำลังยกเลิก…" : "ยกเลิกและกลับไปที่ร้านค้า"}
            </button>
          </div>

          <p className="tiny muted bankpay-note">
            <Icon name="info" size={14} /> หน้านี้เป็นของจำลองสำหรับทดสอบ ยังไม่ได้ต่อกับธนาคารจริง —
            ไม่มีการตัดเงินเกิดขึ้น
          </p>
          <Link to={`/q/${pay.quotation_no}${qs}`} className="tiny muted">กลับไปดูใบเสนอราคา</Link>
        </div>
      </div>
    </main>
  );
}

const METHOD_LABEL: Record<string, string> = {
  qr_promptpay: "QR PromptPay",
  card: "บัตรเครดิต/เดบิต",
  installment: "ผ่อน 0% 10 เดือน",
};
