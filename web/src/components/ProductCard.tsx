import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { useCart } from "../lib/cart";
import { baht, num } from "../lib/format";
import type { MaterialCard } from "../lib/types";
import { useWishlist } from "../lib/wishlist";
import Icon from "./Icon";
import Placeholder from "./Placeholder";

type Props = { item: MaterialCard; action?: ReactNode; compact?: boolean };

export default function ProductCard({ item, action, compact }: Props) {
  const auth = useAuth();
  const cart = useCart();
  const wish = useWishlist(!!auth.user);
  const [adding, setAdding] = useState<"" | "busy" | "done">("");
  const isStaff = auth.role === "sales" || auth.role === "manager" || auth.role === "admin";
  const stock = item.stock;
  const inStock = !!stock && stock.available_total > 0;
  const storeStock = !!stock && stock.store_available > 0;
  const wished = wish.has(item.matnr);

  const toggleWish = (e: React.MouseEvent) => {
    e.preventDefault();
    if (!auth.user) return auth.openLogin();
    void wish.toggle(item.matnr);
  };

  // ลงตะกร้าได้จากการ์ดเลย ไม่ต้องเข้าไปหน้าสินค้าก่อน — วิธีรับสินค้าเลือกให้ตามชนิดของ
  // (ตัวที่ต้องให้ช่างติดตั้งลงเป็น install) เข้าไปแก้ทีหลังได้ในตะกร้า
  const quickAdd = async (e: React.MouseEvent) => {
    e.preventDefault();
    setAdding("busy");
    try {
      await cart.add(item.matnr, { qty: 1, supply_mode: item.requires_install ? "install" : "ship" });
      setAdding("done");
      // ลงแล้วขึ้นทางลัด "ไปที่ตะกร้า" ให้กดต่อได้ ถ้าไม่กดก็หายไปเองแล้วกลับเป็นปุ่มลงตะกร้าตามเดิม
      setTimeout(() => setAdding(""), 4000);
    } catch {
      setAdding("");
    }
  };

  return (
    <article className={"pcard" + (compact ? " compact" : "")}>
      <Link to={`/p/${item.matnr}`} className="pcard-img">
        <Placeholder src={item.image_url} alt={item.name_th} label={<>PRODUCT SHOT<br />1:1</>} />
        {item.is_new && !item.discount_percent ? <span className="pcard-new">NEW</span> : null}
      </Link>
      <button className={"pcard-wish" + (wished ? " on" : "")} onClick={toggleWish} aria-label={wished ? "เอาออกจากรายการโปรด" : "เก็บใส่รายการโปรด"}>
        <Icon name="favorite" size={18} />
      </button>
      <div className="pcard-body">
        <Link to={`/p/${item.matnr}`} className="pcard-name">{item.name_th}</Link>
        <div className="pcard-brand">{item.brand_name || "SB DESIGN"}</div>
        {/* รุ่น/ขนาด กับ ราคาปกติ มีบ้างไม่มีบ้าง — เว้นที่ไว้เสมอ การ์ดในแถวเดียวกันจะได้อยู่ระดับเดียวกัน */}
        <div className="pcard-variant">{[item.variant, item.spec].filter(Boolean).join(" · ")}</div>
        <div className="pcard-price">
          <span className="now">{baht(item.price)}</span>
          {item.discount_percent ? <span className="off">ลด {item.discount_percent}%</span> : null}
        </div>
        <div className="pcard-was">{item.compare_at_price ? <>ราคาปกติ <s>{baht(item.compare_at_price)}</s></> : null}</div>
        {item.member_price && item.price_tier !== "standard" ? (
          <div className="pcard-member">ราคาสมาชิก {item.price_tier} · ประหยัด {baht(num(item.standard_price) - num(item.price))}</div>
        ) : item.member_price && num(item.member_price) < num(item.price) ? (
          <div className="pcard-member">สมาชิก {baht(item.member_price)}</div>
        ) : null}
        {num(item.price) >= 10000 && <div className="pcard-note">ผ่อน 0% 10 เดือน</div>}
        {/* สต็อกมาจาก cache — สินค้าส่วนใหญ่ยังไม่เคยถูกเช็ค บอกว่า "สั่งจอง" ทั้งที่ไม่รู้จริงไม่ได้ */}
        {stock && (
          <div className={"pcard-stock " + (inStock ? "ok" : "no")}>
            {inStock ? (storeStock ? "มีของที่สาขา · พร้อมส่ง" : "สั่งจากคลัง · รอจัดส่ง") : "สั่งจอง / ของเข้ารอบถัดไป"}
          </div>
        )}
        {/* หน้าเซลล์ส่งปุ่มของตัวเองมาทาง action (ลงตะกร้าลูกค้าที่ดูแลอยู่) — ไม่ซ้อนปุ่มลงตะกร้าตัวเอง */}
        {action ? (
          <div className="pcard-action">{action}</div>
        ) : isStaff ? null : (
          <div className="pcard-action">
            {adding === "done" ? (
              <Link to="/cart" className="btn sm block green" onClick={(e) => e.stopPropagation()}>
                <Icon name="shopping_cart" size={16} /> ไปที่ตะกร้า
              </Link>
            ) : (
              <button className="btn sm block" onClick={quickAdd} disabled={adding === "busy"}>
                <Icon name="add_shopping_cart" size={16} />
                {adding === "busy" ? "กำลังเพิ่ม…" : "ลงตะกร้า"}
              </button>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
