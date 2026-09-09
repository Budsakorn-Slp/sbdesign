import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import Icon from "../components/Icon";
import ProductCard from "../components/ProductCard";
import ProductRow from "../components/ProductRow";
import { apiGet, errorMessage } from "../lib/api";
import { useContent } from "../lib/content";
import type { MaterialCard, SearchOut } from "../lib/types";

const PAGE = 48;
const TOP = 10; // จำนวนการ์ดในแถวขายดี (โชว์ทีละ 5 ที่เหลือเลื่อนดู)

const TAG_LABEL: Record<string, string> = { deal: "ดีลพิเศษ", new: "สินค้าใหม่", bestseller: "สินค้าขายดี" };
const ROOM_LABEL: Record<string, string> = { bedroom: "ห้องนอน", living: "ห้องนั่งเล่น", dining: "ห้องทานอาหาร / ครัว", office: "โฮมออฟฟิศ", outdoor: "นอกบ้าน", kids: "เด็ก" };

const SORTS: { key: string; label: string }[] = [
  { key: "relevance", label: "แนะนำ" },
  { key: "bestseller", label: "ขายดี" },
  { key: "new", label: "มาใหม่" },
  { key: "price_asc", label: "ราคาต่ำ → สูง" },
  { key: "price_desc", label: "ราคาสูง → ต่ำ" },
  { key: "discount", label: "ส่วนลดมากสุด" },
];

/** ตัวเลือกแบบติ๊กเปิด/ปิด ที่เก็บค่าเป็น "1" ใน query string */
const SWITCHES: { key: string; label: string }[] = [
  { key: "discount_only", label: "มีส่วนลด" },
  { key: "in_stock", label: "มีของพร้อมส่ง" },
  { key: "has_image", label: "มีรูปสินค้า" },
];

/** แถวการ์ดแนวนอน 10 ตัว — เลื่อนดูได้ ความกว้างช่องหารตามจอ การ์ดจะได้ไม่โดนตัดครึ่ง */
function TopRow({ title, path, more }: { title: string; path: string; more: string }) {
  const [items, setItems] = useState<MaterialCard[] | null>(null);

  useEffect(() => {
    let alive = true;
    apiGet<SearchOut>(path)
      .then((d) => alive && setItems(d.items))
      .catch(() => alive && setItems([]));
    return () => {
      alive = false;
    };
  }, [path]);

  if (!items) return <div className="ph" style={{ height: 260 }} />;
  return <ProductRow title={title} items={items} more={more} />;
}

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const { content } = useContent();
  const q = params.get("q") || "";
  const category = params.get("category") || "";
  const room = params.get("room") || "";
  const tag = params.get("tag") || "";
  const sort = params.get("sort") || "relevance";
  const brands = params.getAll("brand");

  const [data, setData] = useState<SearchOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [brandQ, setBrandQ] = useState("");
  const [allBrands, setAllBrands] = useState(false);
  const [drawer, setDrawer] = useState(false); // แผงตัวกรองบนจอเล็ก
  const sentinel = useRef<HTMLDivElement | null>(null);
  // กันยิงซ้ำ: state ช้าไปหนึ่งจังหวะ observer ยิงติดกันได้ก่อน re-render
  const busy = useRef(false);

  // ตัวกรองทั้งชุดในรูป query string — เปลี่ยนตัวไหนก็ค้นใหม่ทั้งหมด
  const filterQs = useMemo(() => {
    const qs = new URLSearchParams();
    for (const [k, v] of params) if (k !== "sort" && v) qs.append(k, v);
    if (sort !== "relevance") qs.set("sort", sort);
    return qs.toString();
  }, [params, sort]);

  const fetchPage = useCallback(
    (offset: number) => {
      const qs = new URLSearchParams(filterQs);
      qs.set("limit", String(PAGE));
      qs.set("offset", String(offset));
      if (!offset) qs.set("facets", "1"); // ขอ facet แค่หน้าแรก หน้าถัดไปนับซ้ำเปล่าๆ
      return apiGet<SearchOut>(`/materials/search?${qs.toString()}`);
    },
    [filterQs],
  );

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    busy.current = false;
    fetchPage(0)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(errorMessage(e)));
    return () => {
      alive = false;
    };
  }, [fetchPage]);

  const loadMore = useCallback(() => {
    if (busy.current || !data || data.items.length >= data.total) return;
    busy.current = true;
    setLoadingMore(true);
    fetchPage(data.items.length)
      .then((d) =>
        setData((prev) => {
          if (!prev) return d;
          // ต้นทางอาจเปลี่ยนระหว่างเลื่อน — กัน key ซ้ำไว้ก่อน React จะได้ไม่เตือน
          const seen = new Set(prev.items.map((it) => it.matnr));
          return { ...prev, total: d.total, items: [...prev.items, ...d.items.filter((it) => !seen.has(it.matnr))] };
        }),
      )
      .catch((e) => setError(errorMessage(e)))
      .finally(() => {
        busy.current = false;
        setLoadingMore(false);
      });
  }, [data, fetchPage]);

  // infinite scroll — เฝ้าตัวคั่นท้ายกริด พอโผล่เข้าจอก็โหลดหน้าถัดไป
  // rootMargin 400px = เริ่มโหลดก่อนถึงจริง ผู้ใช้เลื่อนต่อได้ไม่สะดุด
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver((entries) => entries[0]?.isIntersecting && loadMore(), { rootMargin: "400px" });
    io.observe(el);
    return () => io.disconnect();
  }, [loadMore]);

  const cats = content?.categories || [];
  const catObj = cats.find((c) => c.id === category) || cats.flatMap((c) => c.children).find((c) => c.id === category);
  const parent = cats.find((c) => c.id === category || c.children.some((ch) => ch.id === category));
  const title = q ? `ผลการค้นหา “${q}”` : catObj ? catObj.name_th : room ? ROOM_LABEL[room] || room : tag ? TAG_LABEL[tag] || tag : "สินค้าทั้งหมด";

  // แถวขายดีต้องเป็น "ขายดีของหมวดที่กำลังดู" ไม่ใช่ขายดีทั้งเว็บ — ผูกกับหมวด/ห้อง/แท็ก/คำค้น
  // ไม่ผูกกับแบรนด์และตัวเลือกเสริม เพราะนั่นเป็นการกรองผลลัพธ์ ไม่ใช่หัวข้อของหน้า
  const topRow = useMemo(() => {
    const scope = new URLSearchParams();
    for (const [k, v] of Object.entries({ q, category, room, tag })) if (v) scope.set(k, v);
    const search = new URLSearchParams(scope);
    search.set("sort", "bestseller");
    search.set("has_image", "true");
    search.set("limit", String(TOP));
    const scoped = scope.toString();
    return {
      title: q ? "สินค้าขายดีจากการค้นหานี้" : scoped ? `สินค้าขายดีใน${title}` : "สินค้าขายดี",
      path: `/materials/search?${search.toString()}`,
      more: `/search?${scoped ? scoped + "&" : ""}sort=bestseller`,
    };
  }, [q, category, room, tag, title]);

  /** เปลี่ยนตัวกรองทีไรก็กลับไปหน้าแรกของผลลัพธ์เสมอ (offset อยู่ใน state ไม่ใช่ URL) */
  const set = (key: string, val: string) => {
    const next = new URLSearchParams(params);
    if (val) next.set(key, val);
    else next.delete(key);
    setParams(next);
  };

  const toggleBrand = (id: string) => {
    const next = new URLSearchParams(params);
    const now = next.getAll("brand");
    next.delete("brand");
    for (const b of now.includes(id) ? now.filter((x) => x !== id) : [...now, id]) next.append("brand", b);
    setParams(next);
  };

  const facetBrands = data?.facets?.brands ?? [];
  const brandName = (id: string) => facetBrands.find((b) => b.id === id)?.name ?? id;
  const shown = useMemo(() => {
    const hit = brandQ.trim().toLowerCase();
    const list = hit ? facetBrands.filter((b) => b.name.toLowerCase().includes(hit)) : facetBrands;
    return allBrands || hit ? list : list.slice(0, 8);
  }, [facetBrands, brandQ, allBrands]);

  // ชิปสรุปว่ากรองอะไรอยู่ กดกากบาทเพื่อถอดทีละตัว
  const chips: { key: string; label: string; clear: () => void }[] = [
    ...(category ? [{ key: "category", label: catObj?.name_th ?? category, clear: () => set("category", "") }] : []),
    ...(room ? [{ key: "room", label: ROOM_LABEL[room] || room, clear: () => set("room", "") }] : []),
    ...(tag ? [{ key: "tag", label: TAG_LABEL[tag] || tag, clear: () => set("tag", "") }] : []),
    ...brands.map((b) => ({ key: `brand-${b}`, label: brandName(b), clear: () => toggleBrand(b) })),
    ...SWITCHES.filter((s) => params.get(s.key)).map((s) => ({ key: s.key, label: s.label, clear: () => set(s.key, "") })),
  ];

  const clearAll = () => setParams(q ? new URLSearchParams({ q }) : new URLSearchParams());

  const facets = (
    <>
      <div className="facet">
        <h4>หมวดหมู่</h4>
        <ul>
          <li className={!category ? "on" : ""}><button className="link-btn" onClick={() => set("category", "")}>ทั้งหมด</button></li>
          {(parent ? (parent.children.length ? [parent, ...parent.children] : [parent]) : cats).map((c) => (
            <li key={c.id} className={category === c.id ? "on" : ""}>
              <button className="link-btn" onClick={() => set("category", c.id)}>{c.name_th}</button>
            </li>
          ))}
        </ul>
      </div>

      {facetBrands.length > 0 && (
        <div className="facet">
          <h4>แบรนด์</h4>
          {facetBrands.length > 8 && (
            <input className="facet-find" placeholder="ค้นหาแบรนด์" value={brandQ} onChange={(e) => setBrandQ(e.target.value)} />
          )}
          <ul className="checks">
            {shown.map((b) => (
              <li key={b.id}>
                <label>
                  <input type="checkbox" checked={brands.includes(b.id)} onChange={() => toggleBrand(b.id)} />
                  <span className="grow">{b.name}</span>
                  <span className="muted small">{b.count}</span>
                </label>
              </li>
            ))}
          </ul>
          {!brandQ && facetBrands.length > 8 && (
            <button className="link-btn small" onClick={() => setAllBrands(!allBrands)}>
              {allBrands ? "ย่อรายการ" : `ดูอีก ${facetBrands.length - 8} แบรนด์`}
            </button>
          )}
        </div>
      )}

      <div className="facet">
        <h4>ตัวเลือกเพิ่มเติม</h4>
        <ul className="checks">
          {SWITCHES.map((s) => (
            <li key={s.key}>
              <label>
                <input type="checkbox" checked={!!params.get(s.key)} onChange={() => set(s.key, params.get(s.key) ? "" : "1")} />
                <span className="grow">{s.label}</span>
              </label>
            </li>
          ))}
        </ul>
      </div>
    </>
  );

  return (
    <main className="container sec search">
      <nav className="crumbs small muted">
        <Link to="/">หน้าแรก</Link> › {parent && parent.id !== category ? <><Link to={`/search?category=${parent.id}`}>{parent.name_th}</Link> › </> : null}<span>{title}</span>
      </nav>
      <div className="search-head">
        <h1>{title}</h1>
        {data && <span className="muted">{data.total.toLocaleString("th-TH")} รายการ</span>}
      </div>

      <div className="search-tools">
        <button className="btn sm filter-btn" onClick={() => setDrawer(true)}>
          <Icon name="tune" size={18} /> ตัวกรอง{chips.length ? ` (${chips.length})` : ""}
        </button>
        <div className="chips grow">
          {chips.map((c) => (
            <button key={c.key} className="chip on" onClick={c.clear}>{c.label} <Icon name="close" size={14} /></button>
          ))}
          {chips.length > 0 && <button className="link-btn small" onClick={clearAll}>ล้างทั้งหมด</button>}
        </div>
        <label className="sortbox">
          <span className="muted small">เรียงตาม</span>
          <select value={sort} onChange={(e) => set("sort", e.target.value === "relevance" ? "" : e.target.value)}>
            {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </label>
      </div>

      <div className="search-body">
        <aside className={"facets" + (drawer ? " open" : "")}>
          <div className="facets-head">
            <strong>ตัวกรอง</strong>
            <button className="link-btn" onClick={() => setDrawer(false)} aria-label="ปิด"><Icon name="close" size={20} /></button>
          </div>
          {facets}
        </aside>
        {drawer && <div className="scrim" onClick={() => setDrawer(false)} />}

        <div className="grow">
          <TopRow title={topRow.title} path={topRow.path} more={topRow.more} />

          {error && <div className="note err">{error}</div>}
          {!data && !error && <div className="ph" style={{ height: 320 }}>กำลังค้นหา…</div>}
          {data && data.items.length === 0 && (
            <div className="card flat" style={{ textAlign: "center", padding: 48 }}>
              <div className="strong">ไม่พบสินค้าที่ตรงกับ “{q || title}”</div>
              <p className="muted small">ลองลดตัวกรอง หรือค้นด้วยชื่อรุ่น รหัสสินค้า (MATNR) หรือบาร์โค้ด</p>
              {chips.length > 0 && <button className="btn sm" onClick={clearAll}>ล้างตัวกรองทั้งหมด</button>}
            </div>
          )}
          {data && data.items.length > 0 && (
            <>
              <div className="pgrid">
                {data.items.map((it) => (
                  <ProductCard key={it.matnr} item={it} />
                ))}
              </div>
              <div ref={sentinel} style={{ height: 1 }} />
              <div className="search-more">
                <div className="muted small">
                  {data.items.length >= data.total ? `แสดงครบ ${data.total.toLocaleString("th-TH")} รายการ` : `${data.items.length} จาก ${data.total.toLocaleString("th-TH")} รายการ`}
                </div>
                {/* ปกติเลื่อนถึงก็โหลดเอง — ปุ่มนี้เป็นทางสำรองเผื่อ IntersectionObserver
                    ไม่ทำงาน (เบราว์เซอร์เก่า / แท็บพื้นหลัง) จะได้ไม่ตันอยู่แค่หน้าแรก */}
                {data.items.length < data.total && (
                  <button className="btn" onClick={loadMore} disabled={loadingMore}>
                    {loadingMore ? "กำลังโหลด…" : "ดูเพิ่มเติม"}
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </main>
  );
}
