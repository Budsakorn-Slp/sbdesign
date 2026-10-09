import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Icon from "../components/Icon";
import { ORDER_TONE, OrderItem } from "../components/OrderCard";
import { apiGet, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { baht, thDateTime } from "../lib/format";
import type { OrderHistory } from "../lib/types";

const STEP_ICON: Record<string, string> = {
  ordered: "receipt_long", paid: "payments", confirmed: "task_alt", in_production: "inventory_2",
  shipping: "local_shipping", delivered: "home", cancelled: "cancel",
};

/** รายละเอียดคำสั่งซื้อ (แบบ Shopee) — ไทม์ไลน์สถานะ · เลขที่/เวลา · ที่อยู่จัดส่ง · สินค้า · สรุปยอด */
export default function OrderDetailPage() {
  const { key = "" } = useParams();
  const auth = useAuth();
  const [o, setO] = useState<OrderHistory | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!auth.ready || !auth.user) return;
    apiGet<OrderHistory>(`/me/orders/${encodeURIComponent(key)}`).then(setO).catch((e) => setErr(errorMessage(e)));
  }, [key, auth.ready, auth.user]);

  const back = <Link to="/account/orders" className="row small muted od-back"><Icon name="arrow_back" size={18} /> ประวัติการสั่งซื้อ</Link>;
  if (err) return <main className="container sec">{back}<div className="note err">{err}</div></main>;
  if (!o) return <main className="container sec">{back}<div className="ph" style={{ height: 240 }}>กำลังโหลด…</div></main>;

  const rows: [string, React.ReactNode][] = [
    ["เลขคำสั่งซื้อ", o.order_no || <span className="muted">รอยืนยันจากระบบ</span>],
    ...(o.quotation_no ? [["เลขที่ใบสั่งซื้อ", <Link to={`/quotations/${o.quotation_no}`}>{o.quotation_no}</Link>] as [string, React.ReactNode]] : []),
    ["สั่งเมื่อ", thDateTime(o.ordered_at || o.order_date)],
    ["ชำระเงิน", o.paid_at ? `${thDateTime(o.paid_at)}${o.payment_method ? ` · ${o.payment_method}` : ""}` : (o.payment_method || "-")],
    ["ช่องทาง", o.channel === "online" ? "สั่งออนไลน์" : `ซื้อที่สาขา${o.branch ? ` · ${o.branch}` : ""}`],
    ...(o.sales_name ? [["พนักงานขาย", o.sales_name] as [string, React.ReactNode]] : []),
  ];

  return (
    <main className="container sec od">
      {back}
      <section className={"od-banner " + (ORDER_TONE[o.status] || "")}>
        <div>
          <b>{o.status_text || o.status}</b>
          <span>{o.status === "delivered" && o.delivery_date ? `ส่งถึงแล้ว ${thDateTime(o.delivery_date)}`
            : o.delivery_date && o.status !== "cancelled" ? `กำหนดส่ง ${thDateTime(o.delivery_date)}` : ""}</span>
        </div>
        <Icon name={STEP_ICON[o.status] || "receipt_long"} size={34} />
      </section>

      <ol className="od-steps">
        {o.steps.map((s) => (
          <li key={s.key} className={(s.done ? "done" : "") + (s.key === "cancelled" ? " cancel" : "")}>
            <span className="od-dot"><Icon name={STEP_ICON[s.key] || "circle"} size={18} /></span>
            <span className="od-label">{s.label}</span>
            {s.at && <span className="od-at">{thDateTime(s.at)}</span>}
          </li>
        ))}
      </ol>

      <div className="od-grid">
        <section className="od-card">
          <h3><Icon name="receipt_long" size={18} /> ข้อมูลคำสั่งซื้อ</h3>
          <dl className="od-dl">{rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
        </section>
        <section className="od-card">
          <h3><Icon name="location_on" size={18} /> ที่อยู่จัดส่ง</h3>
          {o.ship_address ? (
            <>
              <div><b>{o.receiver}</b>{o.phone ? <span className="muted"> · {o.phone}</span> : null}</div>
              <div className="small">{o.ship_address}</div>
            </>
          ) : <div className="small muted">{o.source === "sap" ? "ซื้อที่สาขา — ดูที่อยู่ในใบรับคำสั่งซื้อของสาขา" : "ไม่มีรายการจัดส่ง"}</div>}
          {o.delivery_date && <div className="small" style={{ marginTop: 6 }}>{o.status === "delivered" ? "ส่งถึง" : "กำหนดส่ง"} <b>{thDateTime(o.delivery_date)}</b></div>}
        </section>
      </div>

      <section className="od-card">
        <h3><Icon name="inventory_2" size={18} /> สินค้า ({o.lines.length})</h3>
        <div className="od-items">{o.lines.map((l) => <OrderItem key={l.matnr} l={l} />)}</div>
        <div className="od-sum">
          {o.subtotal !== null && <div><span>รวมสินค้า</span><span>{baht(o.subtotal)}</span></div>}
          {o.discount_total !== null && Number(o.discount_total) > 0 && <div><span>ส่วนลด</span><span className="green">−{baht(o.discount_total)}</span></div>}
          {o.shipping_fee !== null && Number(o.shipping_fee) > 0 && <div><span>ค่าจัดส่ง</span><span>{baht(o.shipping_fee)}</span></div>}
          <div className="od-total"><span>ยอดคำสั่งซื้อทั้งหมด{o.vat !== null ? <small> (รวม VAT {baht(o.vat)})</small> : null}</span><b>{baht(o.grand_total)}</b></div>
        </div>
      </section>
    </main>
  );
}
