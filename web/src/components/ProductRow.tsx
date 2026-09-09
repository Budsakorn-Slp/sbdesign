import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { MaterialCard } from "../lib/types";
import Icon from "./Icon";
import ProductCard from "./ProductCard";

/** แถวสินค้าเลื่อนแนวนอน — หัวข้อซ้าย "ดูทั้งหมด" ขวา ปุ่มลูกศรกลมลอยทับขอบแถว
 *
 * ใช้ร่วมกันทั้งหน้าแรกและหน้าค้นหา จะได้ไม่ต้องมีสองทรง
 */
export default function ProductRow({ title, items, more }: { title: string; items: MaterialCard[]; more?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [edge, setEdge] = useState({ start: true, end: true });

  // ซ่อนลูกศรข้างที่เลื่อนต่อไม่ได้แล้ว ไม่งั้นมีปุ่มกดแล้วไม่ขยับ
  const sync = () => {
    const el = ref.current;
    if (!el) return;
    setEdge({ start: el.scrollLeft < 8, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 8 });
  };
  useEffect(sync, [items]);

  const step = (dir: number) => {
    const el = ref.current;
    if (!el) return;
    el.scrollTo({ left: el.scrollLeft + dir * Math.round(el.clientWidth * 0.8), behavior: "smooth" });
  };

  if (!items.length) return null;
  return (
    <section className="top-row">
      <div className="sec-head">
        <h2>{title}</h2>
        {more && <Link to={more} className="sec-more">ดูทั้งหมด</Link>}
      </div>
      <div className="prow-wrap">
        <div className="pgrid prow" ref={ref} onScroll={sync}>
          {items.map((it) => (
            <ProductCard key={it.matnr} item={it} />
          ))}
        </div>
        {!edge.start && (
          <button className="prow-arrow left" onClick={() => step(-1)} aria-label="ก่อนหน้า"><Icon name="chevron_left" size={20} /></button>
        )}
        {!edge.end && (
          <button className="prow-arrow right" onClick={() => step(1)} aria-label="ถัดไป"><Icon name="chevron_right" size={20} /></button>
        )}
      </div>
    </section>
  );
}
