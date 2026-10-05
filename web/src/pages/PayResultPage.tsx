import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import Icon from "../components/Icon";
import { apiGet, errorMessage } from "../lib/api";
import { bahtWord, thDate } from "../lib/format";
import type { Payment, Quotation } from "../lib/types";

/** หน้าผลการชำระเงิน — สำเร็จ / ไม่สำเร็จ / ยกเลิก / รอผล
 *
 *  สถานะอ่านจากหลังบ้านเสมอ ไม่ได้รับมาทาง query string · ใน URL มีแค่ "เลขรายการไหน"
 *  ถ้าปล่อยให้ส่ง ?status=success มาได้ ใครก็เปิดหน้า "ชำระเงินสำเร็จ" ขึ้นมาเองแล้ว
 *  ถ่ายรูปไปอ้างกับคนอื่นได้ทั้งที่ไม่ได้จ่าย
 */
export default function PayResultPage() {
  const { no = "" } = useParams();
  const [params] = useSearchParams();
  const token = params.get("t");
  const payNo = params.get("p");
  const qs = token ? `?t=${encodeURIComponent(token)}` : "";

  const [q, setQ] = useState<Quotation | null>(null);
  const [pay, setPay] = useState<Payment | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Quotation>(`/quotations/${no}${qs}`).then(setQ).catch((e) => setErr(errorMessage(e)));
    if (payNo) apiGet<Payment>(`/payments/${payNo}${qs}`).then(setPay).catch(() => {});
  }, [no, payNo, qs]);

  if (err) return <main className="container sec"><div className="note err">{err}</div></main>;
  if (!q) return <main className="container sec"><div className="ph" style={{ height: 200 }}>กำลังตรวจสอบผล…</div></main>;

  // ใบที่จ่ายแล้วถือว่าสำเร็จเสมอ ไม่ต้องรอผลรายการล่าสุด — ลูกค้าอาจกดจ่ายซ้ำหลังจ่ายไปแล้ว
  const paid = q.status === "paid" || q.status === "converted";
  const state: keyof typeof VIEW =
    paid ? "paid"
    : pay?.status === "cancelled" ? "cancelled"
    : pay?.status === "failed" ? "failed"
    : pay?.status === "expired" ? "expired"
    : "pending";
  const V = VIEW[state];

  return (
    <main className="container sec">
      <div className={"card pay-done pay-result " + V.cls}>
        <div className="pay-tick"><Icon name={V.icon} size={44} /></div>
        <h1>{V.title}</h1>
        <p className="muted">
          {q.quotation_no}
          {pay ? ` · ${pay.kind === "deposit" ? "มัดจำ 20%" : "เต็มจำนวน"} ${bahtWord(pay.amount)}` : ""}
        </p>

        {state === "paid" && (q.sap_so_no
          ? <div className="note ok">เลขที่คำสั่งซื้อ (SO) <b className="mono">{q.sap_so_no}</b> — ส่งเข้าระบบ SAP แล้ว</div>
          : <div className="note warn">รับเงินเรียบร้อย · กำลังส่งคำสั่งซื้อเข้าระบบ SAP (ระบบจะลองใหม่อัตโนมัติ แล้วแจ้งเลข SO ให้ทางอีเมล)</div>
        )}
        {state === "failed" && (
          <div className="note err">
            {pay?.failed_reason || "ธนาคารปฏิเสธรายการ"}
            <div className="small" style={{ marginTop: 4 }}>ยังไม่มีการตัดเงิน · ใบเสนอราคายังใช้ได้ กดชำระใหม่หรือเปลี่ยนช่องทางได้เลย</div>
          </div>
        )}
        {state === "cancelled" && <div className="note warn">คุณยกเลิกรายการที่หน้าธนาคาร · ยังไม่มีการตัดเงิน และใบเสนอราคายังใช้ได้</div>}
        {state === "expired" && <div className="note warn">รายการหมดอายุ (15 นาที) · กดชำระใหม่เพื่อสร้างรายการอีกครั้ง</div>}
        {state === "pending" && <div className="note warn">ยังไม่ได้รับผลจากธนาคาร — ถ้าจ่ายไปแล้วรอสักครู่แล้วกดดูใหม่ ระบบจะอัปเดตเองเมื่อธนาคารแจ้งผล</div>}

        {state === "paid" && q.slot_date && (
          <p className="small">
            นัดส่ง <b>{thDate(q.slot_date, true)}</b> {q.slot_period === "am" ? "รอบเช้า (09:00–12:00)" : "รอบบ่าย (13:00–17:00)"}
            {q.ship_address ? ` · ${q.ship_address} ${q.ship_postcode || ""}` : ""}
          </p>
        )}

        <div className="row wrap" style={{ gap: 8, marginTop: 12 }}>
          <Link to={`/q/${q.quotation_no}${qs}`} className="btn">ดูใบเสนอราคา</Link>
          {state === "paid"
            ? <Link to="/" className="btn primary">กลับหน้าแรก</Link>
            : <Link to={`/pay/${q.quotation_no}${qs}`} className="btn primary">กลับไปชำระเงิน</Link>}
        </div>
      </div>
    </main>
  );
}

const VIEW = {
  paid: { title: "ชำระเงินสำเร็จ", icon: "check_circle", cls: "ok" },
  failed: { title: "ชำระเงินไม่สำเร็จ", icon: "cancel", cls: "err" },
  cancelled: { title: "ยกเลิกการชำระเงิน", icon: "do_not_disturb_on", cls: "warn" },
  expired: { title: "รายการหมดอายุ", icon: "schedule", cls: "warn" },
  pending: { title: "รอผลการชำระเงิน", icon: "hourglass_top", cls: "warn" },
} as const;
