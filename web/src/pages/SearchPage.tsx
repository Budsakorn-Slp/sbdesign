import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import ProductCard from "../components/ProductCard";
import { apiGet, errorMessage } from "../lib/api";
import { useContent } from "../lib/content";
import type { SearchOut } from "../lib/types";

const TAG_LABEL: Record<string, string> = { deal: "ดีลพิเศษ", new: "สินค้าใหม่", bestseller: "สินค้าขายดี" };
const ROOM_LABEL: Record<string, string> = { bedroom: "ห้องนอน", living: "ห้องนั่งเล่น", dining: "ห้องทานอาหาร / ครัว", office: "โฮมออฟฟิศ", outdoor: "นอกบ้าน", kids: "เด็ก" };

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const { content } = useContent();
  const q = params.get("q") || "";
  const category = params.get("category") || "";
  const room = params.get("room") || "";
  const tag = params.get("tag") || "";
  const [data, setData] = useState<SearchOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    if (category) qs.set("category", category);
    if (room) qs.set("room", room);
    if (tag) qs.set("tag", tag);
    qs.set("limit", "48");
    setData(null);
    setError(null);
    apiGet<SearchOut>(`/materials/search?${qs.toString()}`).then(setData).catch((e) => setError(errorMessage(e)));
  }, [q, category, room, tag]);

  const cats = content?.categories || [];
  const catObj = cats.find((c) => c.id === category) || cats.flatMap((c) => c.children).find((c) => c.id === category);
  const parent = cats.find((c) => c.id === category || c.children.some((ch) => ch.id === category));
  const title = q ? `ผลการค้นหา “${q}”` : catObj ? catObj.name_th : room ? ROOM_LABEL[room] || room : tag ? TAG_LABEL[tag] || tag : "สินค้าทั้งหมด";

  const set = (key: string, val: string) => {
    const next = new URLSearchParams(params);
    if (val) next.set(key, val);
    else next.delete(key);
    setParams(next);
  };

  return (
    <main className="container sec search">
      <nav className="crumbs small muted">
        <Link to="/">หน้าแรก</Link> › {parent && parent.id !== category ? <><Link to={`/search?category=${parent.id}`}>{parent.name_th}</Link> › </> : null}<span>{title}</span>
      </nav>
      <div className="search-head">
        <h1>{title}</h1>
        {data && <span className="muted">{data.total} รายการ</span>}
      </div>

      <div className="search-body">
        <aside className="facets">
          <div className="facet">
            <h4>หมวดหมู่</h4>
            <ul>
              <li className={!category ? "on" : ""}><button className="link-btn" onClick={() => set("category", "")}>ทั้งหมด</button></li>
              {(parent ? parent.children.length ? [parent, ...parent.children] : [parent] : cats).map((c) => (
                <li key={c.id} className={category === c.id ? "on" : ""}>
                  <button className="link-btn" onClick={() => set("category", c.id)}>{c.name_th}</button>
                </li>
              ))}
            </ul>
          </div>
          <div className="facet">
            <h4>ห้อง</h4>
            <ul>
              {Object.entries(ROOM_LABEL).slice(0, 4).map(([k, v]) => (
                <li key={k} className={room === k ? "on" : ""}><button className="link-btn" onClick={() => set("room", room === k ? "" : k)}>{v}</button></li>
              ))}
            </ul>
          </div>
          <div className="facet">
            <h4>โปรโมชั่น</h4>
            <ul>
              {Object.entries(TAG_LABEL).map(([k, v]) => (
                <li key={k} className={tag === k ? "on" : ""}><button className="link-btn" onClick={() => set("tag", tag === k ? "" : k)}>{v}</button></li>
              ))}
            </ul>
          </div>
        </aside>

        <div className="grow">
          {error && <div className="note err">{error}</div>}
          {!data && !error && <div className="ph" style={{ height: 320 }}>กำลังค้นหา…</div>}
          {data && data.items.length === 0 && (
            <div className="card flat" style={{ textAlign: "center", padding: 48 }}>
              <div className="strong">ไม่พบสินค้าที่ตรงกับ “{q || title}”</div>
              <p className="muted small">ลองค้นด้วยชื่อรุ่น รหัสสินค้า (MATNR) หรือบาร์โค้ด</p>
            </div>
          )}
          {data && data.items.length > 0 && (
            <div className="pgrid">
              {data.items.map((it) => (
                <ProductCard key={it.matnr} item={it} />
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
