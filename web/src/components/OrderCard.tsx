import { Link } from "react-router-dom";
import { baht, thDateTime } from "../lib/format";
import { imageSources } from "../lib/images";
import type { OrderHistory, OrderLine } from "../lib/types";
import Icon from "./Icon";
import Placeholder from "./Placeholder";

export const ORDER_TONE: Record<string, string> = {
  paid: "amber", confirmed: "blue", in_production: "blue", shipping: "blue", delivered: "green", cancelled: "red",
};

/** รูปสินค้า + ชื่อ กดเข้าหน้าสินค้าได้ (ถ้ายังมีในเว็บ) */
export function OrderItem({ l, compact = false }: { l: OrderLine; compact?: boolean }) {
  const pic = <Placeholder src={imageSources(l.matnr, l.image_url)} alt={l.name} label={l.name} />;
  const name = <span className="oi-name">{l.name}</span>;
  return (
    <div className={"oi" + (compact ? " compact" : "")}>
      {l.linkable ? <Link to={`/p/${l.matnr}`} className="oi-pic">{pic}</Link> : <span className="oi-pic">{pic}</span>}
      <div className="oi-main">
        {l.linkable ? <Link to={`/p/${l.matnr}`}>{name}</Link> : name}
        <span className="oi-sub">
          {l.variant ? `${l.variant} · ` : ""}รหัส {l.matnr}{l.supply ? ` · ${l.supply}` : ""}
        </span>
        {l.remark && <span className="oi-remark">หมายเหตุ: {l.remark}</span>}
      </div>
      <span className="oi-qty">×{l.qty}</span>
      <b className="oi-price">{baht(l.line_total)}</b>
    </div>
  );
}

/** การ์ดในแท็บประวัติการสั่งซื้อ — แบบ Shopee: หัว (เลข/สถานะ) · สินค้าพร้อมรูป · ยอด + ปุ่มดูรายละเอียด */
export default function OrderCard({ o }: { o: OrderHistory }) {
  const shown = o.lines.slice(0, 2);
  const more = o.lines.length - shown.length;
  return (
    <article className="ord">
      <header className="ord-head">
        <div className="ord-id">
          <Icon name={o.channel === "online" ? "shopping_bag" : "storefront"} size={18} />
          <span>{o.channel === "online" ? "สั่งออนไลน์" : o.branch || "ซื้อที่สาขา"}</span>
          <span className="ord-no">{o.order_no ? `คำสั่งซื้อ ${o.order_no}` : "รอยืนยันเลขคำสั่งซื้อ"}</span>
        </div>
        <span className={"ord-status " + (ORDER_TONE[o.status] || "")}>{o.status_text || o.status}</span>
      </header>
      <Link to={`/account/orders/${o.key}`} className="ord-items">
        {shown.map((l) => <OrderItem key={l.matnr} l={{ ...l, linkable: false }} compact />)}
        {more > 0 && <div className="ord-more">และอีก {more} รายการ</div>}
      </Link>
      <footer className="ord-foot">
        <span className="small muted">สั่งเมื่อ {thDateTime(o.ordered_at || o.order_date)}{o.delivery_date ? ` · ${o.status === "delivered" ? "ส่งถึง" : "กำหนดส่ง"} ${thDateTime(o.delivery_date)}` : ""}</span>
        <span className="ord-total">ยอดคำสั่งซื้อ <b>{baht(o.grand_total)}</b></span>
        <Link to={`/account/orders/${o.key}`} className="btn sm">ดูรายละเอียด</Link>
      </footer>
    </article>
  );
}
