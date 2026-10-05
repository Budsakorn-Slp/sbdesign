import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import Icon from "../components/Icon";
import ProductCard from "../components/ProductCard";
import { ProductCardSkeletonGrid } from "../components/ProductCardSkeleton";
import SuggestFeed from "../components/SuggestFeed";
import { apiGet, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useContent } from "../lib/content";
import type { Category, MaterialCard, SearchOut } from "../lib/types";

// 20 ใบต่อรอบ — ใหญ่พอให้เลื่อนได้ลื่นโดยไม่ยิงถี่ ถ้าเล็กกว่านี้จะยิงบ่อยจนสะดุด
const PAGE = 20;

const TAG_LABEL: Record<string, string> = { deal: "ดีลพิเศษ", new: "สินค้าใหม่", bestseller: "สินค้าขายดี" };
const ROOM_LABEL: Record<string, string> = { bedroom: "ห้องนอน", living: "ห้องนั่งเล่น", dining: "ห้องทานอาหาร / ครัว", office: "โฮมออฟฟิศ", outdoor: "นอกบ้าน", kids: "เด็ก" };
/** ชั้นสินค้าจาก SAP (MAABC) ที่เอามาทำเป็นหน้าของตัวเอง */
const ABC_LABEL: Record<string, string> = { N: "สินค้าใหม่", Z: "สินค้าขายดี" };

/** กลุ่มสินค้าตามตัวขึ้นต้น MATNR — หลังบ้านแปลชื่อกลุ่มเป็นเลขให้ (ดู catalog_matnr_groups) */
const GROUP_LABEL: Record<string, string> = { display: "สินค้าตัวโชว์", consign: "สินค้าฝากขาย", regular: "สินค้าขายปกติ" };

const SORTS: { key: string; label: string }[] = [
  { key: "relevance", label: "แนะนำ" },
  { key: "bestseller", label: "ขายดี" },
  { key: "new", label: "มาใหม่" },
  { key: "price_asc", label: "ราคาต่ำ → สูง" },
  { key: "price_desc", label: "ราคาสูง → ต่ำ" },
  { key: "discount", label: "ส่วนลดมากสุด" },
];

/** ตัวเลือกที่ยกขึ้นมาเป็นชิปกดเร็วบนแถบบนสุด — เอาเฉพาะที่ลูกค้าใช้ตัดสินใจจริง
 * (มีรูปสินค้าไม่อยู่ในนี้ เป็นเครื่องมือของหลังบ้านมากกว่าของคนซื้อ) */
const QUICK: { key: string; label: string }[] = [
  { key: "in_stock", label: "พร้อมส่ง" },
  { key: "discount_only", label: "ลดราคา" },
];

/** ตัวเลือกแบบติ๊กเปิด/ปิด ที่เก็บค่าเป็น "1" ใน query string */
const SWITCHES: { key: string; label: string; staffOnly?: boolean }[] = [
  { key: "discount_only", label: "ลดราคา" },
  { key: "in_stock", label: "พร้อมส่ง" },
  { key: "has_image", label: "มีรูปสินค้า" },
  // ลิสต์ฝั่งพนักงานมีสินค้าสองหมื่นกว่าตัว (ลูกค้าเห็นสามพันกว่า) ของหมดถูกดันไปท้ายสุด
  // ซึ่งแปลว่าเลื่อนหาไม่เจอจริงๆ — ต้องมีตัวกรองให้เรียกดูตรงๆ
  // ลูกค้าไม่ต้องมีเพราะของหมดถูกซ่อนจากลิสต์ลูกค้าอยู่แล้ว ติ๊กไปก็ได้ศูนย์รายการ
  { key: "sold_out", label: "เฉพาะของหมด", staffOnly: true },
];

export default function SearchPage() {
  const isStaff = !!useAuth().user?.is_staff;
  const [params, setParams] = useSearchParams();
  const { content, plant, setPlantCode } = useContent();
  const q = params.get("q") || "";
  const category = params.get("category") || "";
  const room = params.get("room") || "";
  const tag = params.get("tag") || "";
  const sort = params.get("sort") || "relevance";
  const group = params.get("group") || "";
  const abc = params.get("abc") || ""; // ชั้นสินค้าจาก SAP (MAABC) — N = ของเข้าใหม่
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

  /** เลขสุ่มประจำการเปิดหน้านี้หนึ่งครั้ง — ใช้สลับลำดับสินค้าตอนเปิดดูเฉยๆ
   *
   * เกิดครั้งเดียวตอน mount แล้วส่งตัวเดิมไปทุกหน้าของการเลื่อน ไม่งั้นแต่ละหน้าจะเป็นลำดับ
   * คนละชุด ของที่เพิ่งเห็นหน้าแรกจะเด้งมาซ้ำอีกตอนเลื่อนลง · รีเฟรชทีก็ได้เลขใหม่ = ชุดใหม่
   */
  const [seed] = useState(() => 1 + Math.floor(Math.random() * 2147483645));

  // ตัวกรองทั้งชุดในรูป query string — เปลี่ยนตัวไหนก็ค้นใหม่ทั้งหมด
  const filterQs = useMemo(() => {
    const qs = new URLSearchParams();
    for (const [k, v] of params) if (k !== "sort" && v) qs.append(k, v);
    if (sort !== "relevance") qs.set("sort", sort);
    // เลือกสาขาไว้บนหัวเว็บ = อยากเห็นเฉพาะของที่ไปดูที่สาขานั้นได้จริง
    // อยู่นอก query string เพราะเป็นค่าที่ติดตัวผู้ใช้ข้ามหน้า ไม่ใช่ตัวกรองของหน้านี้
    if (plant) qs.set("plant", plant.plant_code);
    // มีคำค้นให้เรียงตามความตรงอยู่แล้ว การสลับลำดับใช้เฉพาะตอนเปิดดูเฉยๆ
    if (!params.get("q") && sort === "relevance") qs.set("seed", String(seed));
    return qs.toString();
  }, [params, sort, seed, plant]);

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
  // ต้นไม้หมวดลึกได้หลายชั้น (หมวดชุดเว็บจริง = ห้องนอน > ที่นอน > ที่นอนสปริง)
  // ค้นแค่สองชั้นแบบเดิมจะหาหมวดชั้นในไม่เจอ แล้วป้ายตัวกรองจะโชว์รหัสดิบ (w-826) แทนชื่อ
  const findCat = (list: Category[], id: string): Category | undefined => {
    for (const c of list) {
      if (c.id === id) return c;
      const hit = findCat(c.children ?? [], id);
      if (hit) return hit;
    }
    return undefined;
  };
  const findParent = (list: Category[], id: string): Category | undefined => {
    for (const c of list) {
      if (c.id === id || (c.children ?? []).some((ch) => ch.id === id)) return c;
      const hit = findParent(c.children ?? [], id);
      if (hit) return hit;
    }
    return undefined;
  };
  const catObj = findCat(cats, category);
  const parent = findParent(cats, category);
  const title = q ? `ผลการค้นหา “${q}”` : catObj ? catObj.name_th : room ? ROOM_LABEL[room] || room : tag ? TAG_LABEL[tag] || tag : group ? GROUP_LABEL[group] || group : abc ? ABC_LABEL[abc] || "สินค้าทั้งหมด" : "สินค้าทั้งหมด";

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
    // ต้องมีชิปบอก ไม่งั้นลูกค้าเลือกสาขาไว้แล้วลืม พอของหายไปครึ่งหนึ่งจะนึกว่าเว็บพัง
    ...(plant ? [{ key: "plant", label: `ตัวโชว์ที่ ${plant.name}`, clear: () => setPlantCode(null) }] : []),
    ...(category ? [{ key: "category", label: catObj?.name_th ?? category, clear: () => set("category", "") }] : []),
    ...(room ? [{ key: "room", label: ROOM_LABEL[room] || room, clear: () => set("room", "") }] : []),
    ...(tag ? [{ key: "tag", label: TAG_LABEL[tag] || tag, clear: () => set("tag", "") }] : []),
    ...brands.map((b) => ({ key: `brand-${b}`, label: brandName(b), clear: () => toggleBrand(b) })),
    ...SWITCHES.filter((s) => params.get(s.key) && (!s.staffOnly || isStaff)).map((s) => ({ key: s.key, label: s.label, clear: () => set(s.key, "") })),
  ];

  // q / group / abc คือ "หัวข้อของหน้า" ไม่ใช่ตัวกรอง — ล้างตัวกรองแล้วต้องยังอยู่หน้าเดิม
  const clearAll = () => setParams(new URLSearchParams({ ...(q ? { q } : {}), ...(group ? { group } : {}), ...(abc ? { abc } : {}) }));

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
          {SWITCHES.filter((s) => !s.staffOnly || isStaff).map((s) => (
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
      </div>

      {/* แถบตัวกรอง: เลื่อนซ้าย-ขวาได้ ส่วนปุ่ม "ตัวกรอง" ตรึงไว้ริมขวาเสมอ
          ตัวเลือกที่กดบ่อยสุด (พร้อมส่ง / ลดราคา) อยู่หน้าสุดให้กดได้เลย ไม่ต้องเปิดแผง
          — แผงเต็มยังอยู่ครบสำหรับแบรนด์/ช่วงราคา ซึ่งยัดลงแถวเดียวไม่ไหว */}
      <div className="search-tools">
        <div className="tool-scroll">
          <label className="sortbox">
            <select value={sort} onChange={(e) => set("sort", e.target.value === "relevance" ? "" : e.target.value)}>
              {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </label>
          {QUICK.map((s) => {
            const on = !!params.get(s.key);
            return (
              <button key={s.key} className={"tool-chip" + (on ? " on" : "")} onClick={() => set(s.key, on ? "" : "1")}>
                {s.label}
              </button>
            );
          })}
          {/* ตัวกรองที่เปิดอยู่จากแผงเต็ม (แบรนด์ ช่วงราคา ฯลฯ) — กดที่ชิปเพื่อเอาออกได้เลย */}
          {chips.filter((c) => !QUICK.some((s) => s.key === c.key)).map((c) => (
            <button key={c.key} className="tool-chip on" onClick={c.clear}>{c.label} <Icon name="close" size={14} /></button>
          ))}
          {chips.length > 0 && <button className="tool-chip ghost" onClick={clearAll}>ล้างทั้งหมด</button>}
        </div>
        <button className="tool-pin" onClick={() => setDrawer(true)} aria-label="ตัวกรอง">
          <Icon name="tune" size={20} />
          <span>ตัวกรอง</span>
          {chips.length > 0 && <i className="tool-dot" />}
        </button>
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
          {/* บอกเสมอว่าระบบทำอะไรกับคำค้นไปบ้าง — แก้ตัวสะกด, ตีความเป็นตัวกรอง, หรือผ่อนเงื่อนไข
              ผลลัพธ์ที่ไม่ตรงเป๊ะแล้วไม่บอก คือที่มาของความรู้สึกว่า "เสิร์ชมั่ว" */}
          {data?.corrected && (
            <div className="note">
              แสดงผลของ <b>“{data.corrected}”</b> · <Link to={`/search?q=${encodeURIComponent(q)}&mode=keyword`}>ค้นด้วย “{q}” แบบตรงตัว</Link>
            </div>
          )}
          {data?.understood && data.understood.labels.length > 0 && (
            <div className="note">
              <span>เข้าใจว่ากำลังหา: </span>
              {data.understood.labels.map((l) => <span key={l} className="chip on" style={{ marginRight: 6 }}>{l}</span>)}
              {data.understood.dropped.length > 0 && (
                <span className="muted small">
                  · ไม่มีของที่ตรงครบทุกข้อ เลยตัด{data.understood.dropped.map((d) => (d === "color" ? "สี" : "ขนาด")).join(" และ ")}ออก
                </span>
              )}
              {" · "}
              <Link to={`/search?q=${encodeURIComponent(q)}&mode=keyword`}>ค้นแบบตรงตัวแทน</Link>
            </div>
          )}
          {data?.relaxed && data.items.length > 0 && (
            <div className="note">ไม่พบสินค้าที่ตรงครบทุกคำ — แสดงสินค้าที่ตรงบางคำแทน</div>
          )}
          {error && <div className="note err">{error}</div>}
          {!data && !error && (
            <div className="pgrid"><ProductCardSkeletonGrid count={PAGE} /></div>
          )}
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
                {/* โครงเปล่าต่อท้ายตอนกำลังโหลดหน้าถัดไป — เห็นทันทีว่ามีของกำลังมา ไม่ใช่จบแค่นี้ */}
                {loadingMore && <ProductCardSkeletonGrid count={Math.min(PAGE, data.total - data.items.length)} />}
              </div>
              <div ref={sentinel} style={{ height: 1 }} />
              <div className="search-more">
                {/* ยังมีของเหลือ = บอกว่าเหลืออีกเท่าไหร่ · ครบแล้ว = บอกแค่ว่าจบ ไม่ต้องทวนจำนวนซ้ำ */}
                <div className="muted small">
                  {data.items.length >= data.total ? "แสดงครบแล้ว" : `${data.items.length} จาก ${data.total.toLocaleString("th-TH")} รายการ`}
                </div>
                {/* ปกติเลื่อนถึงก็โหลดเอง — ปุ่มนี้เป็นทางสำรองเผื่อ IntersectionObserver
                    ไม่ทำงาน (เบราว์เซอร์เก่า / แท็บพื้นหลัง) จะได้ไม่ตันอยู่แค่หน้าแรก */}
                {data.items.length < data.total && (
                  <button className="btn" onClick={loadMore} disabled={loadingMore}>
                    {loadingMore ? "กำลังโหลด…" : "ดูเพิ่มเติม"}
                  </button>
                )}
              </div>
              {/* ผลค้นหาหมดแล้ว (เช่น "สินค้าใหม่" มีแค่ 9 ชิ้น) — ต่อของให้เลื่อนดูได้อีก
                  แยกหัวข้อชัดเจน ไม่เอาไปต่อท้ายกริดเดิม ลูกค้าจะได้ไม่สับสนว่าเป็นผลค้นหาด้วย */}
              {data.items.length >= data.total && <SuggestFeed exclude={data.items.map((it) => it.matnr)} />}
            </>
          )}
        </div>
      </div>
    </main>
  );
}
