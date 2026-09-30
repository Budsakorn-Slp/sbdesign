import { useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { localName, useLang } from "../lib/i18n";
import { useCart } from "../lib/cart";
import { bahtSign, num, realSpec } from "../lib/format";
import { imageSources } from "../lib/images";
import { trackProductClick } from "../lib/track";
import type { MaterialCard } from "../lib/types";
import { useWishlist } from "../lib/wishlist";
import { useLocation } from "react-router-dom";
import Icon from "./Icon";
import Placeholder from "./Placeholder";

type Props = { item: MaterialCard; action?: ReactNode; compact?: boolean };

/** เหลือเท่านี้หรือน้อยกว่า = ขึ้นสีแดง เร่งให้ตัดสินใจ และกันลูกค้าคาดหวังว่าสั่งได้เยอะ */
const LOW_STOCK = 5;

export default function ProductCard({ item, action, compact }: Props) {
  const auth = useAuth();
  const { lang, t } = useLang();
  const loc = useLocation();
  const nav = useNavigate();
  const cart = useCart();
  const wish = useWishlist(!!auth.user);
  const [adding, setAdding] = useState<"" | "busy" | "done">("");
  const isStaff = auth.role === "sales" || auth.role === "manager" || auth.role === "admin";
  // จำนวนของจาก cache (ยอดสดยืนยันอีกทีตอนสั่งซื้อ คนอื่นซื้อตัดหน้าได้ระหว่างนั้น)
  const checked = !!item.stock;
  const ready = item.stock?.ready_qty ?? 0;
  const later = item.stock?.later_qty ?? 0;
  // ยังไม่เคยส่งไปเช็คก็ขึ้นขีดไว้ก่อน — บอกว่า "ยังไม่รู้" ไม่ใช่ "ไม่มีของ"
  const qtyText = checked ? String(ready) : "-";
  // ของหมดแต่มีรอบเข้าถัดไป = พรีออเดอร์ ยังสั่งได้ · หมดแล้วไม่มีรอบเข้า = หมดจริง
  const preOrder = checked && ready <= 0 && (later > 0 || !!item.stock?.made_to_order);
  // หมดจริงปกติถูกกรองออกจากผลค้นหาอยู่แล้ว ที่ยังเจอได้คือตอนพิมพ์รหัสสินค้ามาตรงๆ
  const soldOut = checked && ready <= 0 && later <= 0 && !item.stock?.made_to_order;
  const low = checked && ready > 0 && ready <= LOW_STOCK;
  const wished = wish.has(item.matnr);

  // กดมาจากหน้าไหน — ถ้ามาจากผลค้นหาก็ส่งคำค้นไปด้วย เพื่อวัดว่าคำนั้นค้นแล้วได้ของที่ใช่ไหม
  const onOpen = () => {
    const from = loc.pathname.startsWith("/search") ? "search" : loc.pathname === "/" ? "home" : loc.pathname.startsWith("/p/") ? "related" : "other";
    trackProductClick(item.matnr, from, from === "search" ? new URLSearchParams(loc.search).get("q") || undefined : undefined);
  };

  const toggleWish = (e: React.MouseEvent) => {
    e.preventDefault();
    if (!auth.user) return auth.openLogin();
    void wish.toggle(item.matnr);
  };

  // ลงตะกร้าได้จากการ์ดเลย ไม่ต้องเข้าไปหน้าสินค้าก่อน — วิธีรับสินค้าเลือกให้ตามชนิดของ
  // (ตัวที่ต้องให้ช่างติดตั้งลงเป็น install) เข้าไปแก้ทีหลังได้ในตะกร้า
  // ซื้อเลย = ลงตะกร้าแล้วพาไปหน้าชำระเงินต่อทันที ไม่ต้องแวะหน้าตะกร้า
  // ยังไม่ล็อกอินก็เก็บของใส่ตะกร้าไว้ก่อนแล้วเปิดหน้าล็อกอิน — หน้าชำระเงินรับเฉพาะลูกค้าที่ล็อกอินแล้ว
  // (ถ้าปล่อยไปเลยจะโดนเด้งกลับมาหน้าตะกร้าเฉยๆ ลูกค้าไม่รู้ว่าทำไม)
  const buyNow = async (e: React.MouseEvent) => {
    e.preventDefault();
    setAdding("busy");
    try {
      await cart.add(item.matnr, { qty: 1, supply_mode: item.requires_install ? "install" : "ship" });
      if (auth.role === "customer") nav("/checkout");
      else {
        setAdding("done");
        auth.openLogin();
      }
    } catch {
      setAdding("");
    }
  };

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
    <article className={"pcard" + (compact ? " compact" : "") + (soldOut ? " sold-out" : "")}>
      {soldOut ? (
        <div className="pcard-img">
          <Placeholder src={imageSources(item.matnr, item.image_url)} alt={localName(lang, item.name_th, item.name_en)} label={<>PRODUCT SHOT<br />1:1</>} />
          <span className="pcard-soldout">{t("สินค้าหมด")}</span>
        </div>
      ) : (
        <Link to={`/p/${item.matnr}`} className="pcard-img" onClick={onOpen}>
          <Placeholder src={imageSources(item.matnr, item.image_url)} alt={localName(lang, item.name_th, item.name_en)} label={<>PRODUCT SHOT<br />1:1</>} />
          {item.is_new && !item.discount_percent && !item.is_display ? <span className="pcard-new">NEW</span> : null}
          {/* ของตั้งโชว์หน้าร้าน ไม่ใช่ของใหม่ในกล่อง — ต้องเห็นตั้งแต่ในผลค้นหา ไม่ใช่ไปรู้ตอนจ่ายเงิน */}
          {item.is_display ? <span className="pcard-display">สินค้าตัวโชว์</span> : null}
        </Link>
      )}
      <button className={"pcard-wish" + (wished ? " on" : "")} onClick={toggleWish} aria-label={wished ? "เอาออกจากรายการโปรด" : "เก็บใส่รายการโปรด"}>
        {/* fill = หัวใจทึบ · Material Symbols ขึ้นเป็นเส้นขอบเสมอถ้าไม่สั่ง
            เส้นขอบสีแดงดูไม่ต่างจากสีเข้มปกติเท่าไหร่ ต้องทึบถึงจะเห็นชัดว่ากดไปแล้ว */}
        <Icon name="favorite" size={18} fill={wished} />
      </button>
      <div className="pcard-body">
        {soldOut ? (
          <span className="pcard-name">{localName(lang, item.name_th, item.name_en)}</span>
        ) : (
          <Link to={`/p/${item.matnr}`} className="pcard-name" onClick={onOpen}>{localName(lang, item.name_th, item.name_en)}</Link>
        )}
        <div className="pcard-brand">{item.brand_name || "SB DESIGN"}</div>
        {/* รุ่น/ขนาด กับ ราคาปกติ มีบ้างไม่มีบ้าง — เว้นที่ไว้เสมอ การ์ดในแถวเดียวกันจะได้อยู่ระดับเดียวกัน */}
        <div className="pcard-variant">{[item.variant, realSpec(item.spec)].filter(Boolean).join(" · ")}</div>
        {/* ราคาอยู่ริมซ้าย ตัวใหญ่สุดในการ์ด แล้วตามด้วยราคาเต็มขีดฆ่ากับ % ที่ลด — เรียงแบบนี้
            เพราะสายตาอ่านราคาจริงก่อนเสมอ ส่วนราคาเต็มกับ % เป็นของประกอบที่อ่านทีหลัง
            บรรทัดล่างเป็นสต็อก (ที่เว็บอื่นใช้โชว์ดาวรีวิว) — เรายังไม่มีรีวิว แต่จำนวนของที่เหลือ
            เป็นข้อมูลที่ช่วยตัดสินใจจริงกว่า · ตัวเลขมาจาก product_stock (อายุไม่เกิน TTL)
            ยอดสดยืนยันอีกทีตอนสั่งซื้อ */}
        <div className="pcard-price">
          <span className="now">{bahtSign(item.price)}</span>
          {item.compare_at_price ? <s className="was">{bahtSign(item.compare_at_price)}</s> : null}
          {item.discount_percent ? <span className="off">-{item.discount_percent}%</span> : null}
        </div>
        <div className="pcard-stock">
          <span className={"pcard-badge " + (!checked ? "unknown" : soldOut ? "no" : preOrder ? "pre" : low ? "low" : "ok")}>
            {soldOut ? "สินค้าหมด" : preOrder ? "พรีออเดอร์" : `มีสต็อก ${qtyText} ชิ้น`}
          </span>
        </div>
        {num(item.price) >= 10000 && <div className="pcard-note">ผ่อน 0% 10 เดือน</div>}
        {/* หน้าเซลล์ส่งปุ่มของตัวเองมาทาง action (ลงตะกร้าลูกค้าที่ดูแลอยู่) — ไม่ซ้อนปุ่มลงตะกร้าตัวเอง */}
        {action ? (
          <div className="pcard-action">{action}</div>
        ) : soldOut ? (
          <div className="pcard-action">
            <button className="btn sm block" disabled>{t("สินค้าหมด")}</button>
          </div>
        ) : isStaff ? null : (
          <div className="pcard-action">
            {adding === "done" ? (
              <Link to="/cart" className="btn sm block green" onClick={(e) => e.stopPropagation()}>
                <Icon name="shopping_cart" size={16} /> ไปที่ตะกร้า
              </Link>
            ) : (
              <div className="pcard-btns">
                <button className="btn sm" onClick={quickAdd} disabled={adding !== ""} aria-label="ลงตะกร้า">
                  <Icon name="add_shopping_cart" size={16} />
                  <span className="pcard-btn-label">{adding === "busy" ? "กำลังเพิ่ม…" : preOrder ? "พรีออเดอร์" : "ลงตะกร้า"}</span>
                </button>
                <button className="btn sm dark" onClick={buyNow} disabled={adding !== ""}>{t("ซื้อเลย")}</button>
              </div>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
