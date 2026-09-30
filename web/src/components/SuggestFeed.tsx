import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ProductCard from "./ProductCard";
import { ProductCardSkeletonGrid } from "./ProductCardSkeleton";
import { apiGet } from "../lib/api";
import type { MaterialCard, SearchOut } from "../lib/types";

const PAGE = 20;

/** แถบ "สินค้าที่คุณอาจจะสนใจ" ต่อท้ายผลค้นหาที่แสดงครบแล้ว
 *
 * มีไว้ให้ลูกค้าเลื่อนดูของต่อได้ ไม่ใช่เจอทางตันเมื่อผลค้นหามีไม่กี่ชิ้น
 * แยกหัวข้อกับเส้นคั่นชัดเจน เพราะของพวกนี้ "ไม่ได้ตรงกับที่ค้น" ถ้าต่อท้ายกริดเดิมเฉยๆ
 * ลูกค้าจะนึกว่าเป็นผลค้นหาด้วย แล้วงงว่าทำไมของไม่ตรงคำที่พิมพ์
 *
 * ลำดับสุ่มด้วย seed ที่สุ่มครั้งเดียวตอนเปิด — เลื่อนหน้าถัดไปของจะไม่ซ้ำ/ไม่หาย
 * (ดู _shuffle ใน catalog_service) และเข้าใหม่อีกครั้งก็ได้ของคนละชุด
 */
export default function SuggestFeed({ exclude }: { exclude: string[] }) {
  const [seed] = useState(() => Math.floor(Math.random() * 2147483646) + 1);
  const [items, setItems] = useState<MaterialCard[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const offset = useRef(0);
  const busy = useRef(false);
  const sentinel = useRef<HTMLDivElement>(null);

  // ตัวที่อยู่ในผลค้นหาด้านบนอยู่แล้วต้องไม่โผล่ซ้ำ — ทำเป็น Set ไว้ครั้งเดียว
  // ไม่ผูกกับ identity ของ array ที่เปลี่ยนทุก render ไม่งั้น loop โหลดไม่จบ
  const skip = useMemo(() => new Set(exclude), [exclude.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(() => {
    if (busy.current || (total !== null && offset.current >= total)) return;
    busy.current = true;
    setLoading(true);
    apiGet<SearchOut>(`/materials/search?seed=${seed}&limit=${PAGE}&offset=${offset.current}`)
      .then((d) => {
        offset.current += PAGE;
        setTotal(d.total);
        setItems((prev) => {
          const seen = new Set([...skip, ...prev.map((p) => p.matnr)]);
          return [...prev, ...d.items.filter((it) => !seen.has(it.matnr))];
        });
      })
      .catch(() => setTotal(0)) // พังก็แค่ไม่มีแถบนี้ ไม่ให้กระทบผลค้นหาด้านบน
      .finally(() => {
        busy.current = false;
        setLoading(false);
      });
  }, [seed, total, skip]);

  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver((e) => e[0]?.isIntersecting && load(), { rootMargin: "400px" });
    io.observe(el);
    return () => io.disconnect();
  }, [load]);

  if (total === 0 && !items.length) return null;
  return (
    <section className="suggest-feed">
      <div className="sec-head">
        <h2>สินค้าที่คุณอาจจะสนใจ</h2>
      </div>
      <div className="pgrid">
        {items.map((it) => (
          <ProductCard key={it.matnr} item={it} />
        ))}
        {loading && <ProductCardSkeletonGrid count={PAGE} />}
      </div>
      <div ref={sentinel} style={{ height: 1 }} />
    </section>
  );
}
