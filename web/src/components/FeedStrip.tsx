import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import ProductCard from "./ProductCard";
import { apiGet } from "../lib/api";
import type { MaterialCard } from "../lib/types";

type Props = { title: string; path: string; more?: string; limit?: number; deps?: unknown[] };

/** แถบสินค้าที่ดึงสดจาก API (ขายดี / ดูล่าสุด / ซื้อซ้ำ) — ว่างเมื่อไหร่ก็ไม่ต้องแสดง */
export default function FeedStrip({ title, path, more, limit = 4, deps = [] }: Props) {
  const [items, setItems] = useState<MaterialCard[]>([]);

  useEffect(() => {
    apiGet<MaterialCard[]>(path).then(setItems).catch(() => setItems([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);

  if (!items.length) return null;
  return (
    <section className="container sec">
      <div className="sec-head">
        <h2>{title}</h2>
        {more && <Link to={more} className="sec-more">ดูทั้งหมด ›</Link>}
      </div>
      <div className="pgrid">
        {items.slice(0, limit).map((it) => (
          <ProductCard key={it.matnr} item={it} />
        ))}
      </div>
    </section>
  );
}
