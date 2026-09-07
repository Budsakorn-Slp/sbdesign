import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { baht, num } from "../lib/format";
import type { MaterialCard } from "../lib/types";
import Placeholder from "./Placeholder";

type Props = { item: MaterialCard; action?: ReactNode; compact?: boolean };

export default function ProductCard({ item, action, compact }: Props) {
  const stock = item.stock;
  const inStock = !!stock && stock.available_total > 0;
  const storeStock = !!stock && stock.store_available > 0;
  return (
    <article className={"pcard" + (compact ? " compact" : "")}>
      <Link to={`/p/${item.matnr}`} className="pcard-img">
        <Placeholder src={item.image_url} alt={item.name_th} label={<>PRODUCT SHOT<br />1:1</>} />
        {item.discount_percent ? <span className="pcard-off">-{item.discount_percent}%</span> : null}
        {item.is_new && !item.discount_percent ? <span className="pcard-new">NEW</span> : null}
      </Link>
      <div className="pcard-body">
        <div className="pcard-brand">{item.brand_name || "SB DESIGN"}</div>
        <Link to={`/p/${item.matnr}`} className="pcard-name">{item.name_th}</Link>
        {item.variant && <div className="pcard-variant">{item.variant}{item.spec ? ` · ${item.spec}` : ""}</div>}
        <div className="pcard-price">
          <span className="now">{baht(item.price)}</span>
          {item.compare_at_price && <span className="was">{baht(item.compare_at_price)}</span>}
        </div>
        {item.member_price && item.price_tier !== "standard" ? (
          <div className="pcard-member">ราคาสมาชิก {item.price_tier} · ประหยัด {baht(num(item.standard_price) - num(item.price))}</div>
        ) : item.member_price && num(item.member_price) < num(item.price) ? (
          <div className="pcard-member">สมาชิก {baht(item.member_price)}</div>
        ) : null}
        {num(item.price) >= 10000 && <div className="pcard-note">ผ่อน 0% 10 เดือน</div>}
        <div className={"pcard-stock " + (inStock ? "ok" : "no")}>
          {inStock ? (storeStock ? "มีของที่สาขา · พร้อมส่ง" : "สั่งจากคลัง · รอจัดส่ง") : "สั่งจอง / ของเข้ารอบถัดไป"}
        </div>
        {action && <div className="pcard-action">{action}</div>}
      </div>
    </article>
  );
}
