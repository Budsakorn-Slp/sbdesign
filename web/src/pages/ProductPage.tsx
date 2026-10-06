import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import BranchPhotos from "../components/BranchPhotos";
import StaffPhotos from "../components/StaffPhotos";
import Icon from "../components/Icon";
import Placeholder from "../components/Placeholder";
import ProductCard from "../components/ProductCard";
import ProductRow from "../components/ProductRow";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import { imageSources, normalizeImageUrl } from "../lib/images";
import { useAuth } from "../lib/auth";
import { useCart } from "../lib/cart";
import { useContent } from "../lib/content";
import { baht, num, realSpec, thDate } from "../lib/format";
import { useSales } from "../lib/sales";
import type { MaterialCard, MaterialDetail, SearchOut, SupplyMode } from "../lib/types";

const FEED_PAGE = 24;
/** จำนวนแหล่งที่ยอมไล่ต่อการโหลดหนึ่งครั้ง — กันกรณีแหล่งต้นๆ คืนแต่ของซ้ำจนต้องข้ามยาว */
const FEED_MAX_HOPS = 6;

/** "167.5X40X75" → "กว้าง 167.5 × ลึก 40 × สูง 75 ซม." — ต้นทางเก็บเป็นสตริงเดียว (GROES) */
function sizeText(raw: string | null): string | null {
  const spec = realSpec(raw);
  if (!spec) return null;
  const parts = spec.split(/[xX*×]/).map((s) => s.trim()).filter(Boolean);
  if (parts.length !== 3 || parts.some((p) => !/^[\d.]+$/.test(p))) return spec;
  const [w, d, h] = parts;
  return `กว้าง ${w} × ลึก ${d} × สูง ${h} ซม.`;
}

/** หัวข้อพับได้ — ใช้ <details> ของเบราว์เซอร์ กดด้วยคีย์บอร์ด/อ่านด้วย screen reader ได้เอง */
function Acc({ title, children, open }: { title: string; children: ReactNode; open?: boolean }) {
  return (
    <details className="acc" open={open}>
      <summary>
        <span className="grow">{title}</span>
        <Icon name="expand_more" size={20} />
      </summary>
      <div className="acc-body">{children}</div>
    </details>
  );
}

function SpecRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="spec-row">
      <span className="muted">{label}</span>
      <span className="grow">{value}</span>
    </div>
  );
}

export default function ProductPage() {
  const { matnr = "" } = useParams();
  const nav = useNavigate();
  const auth = useAuth();
  const cart = useCart();
  const sales = useSales();
  const { plant } = useContent();
  const [item, setItem] = useState<MaterialDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  /* สต็อกมากับข้อมูลสินค้าแล้ว ไม่ต้องยิงเพิ่ม
   *
   * ของเดิมเปิดหน้าสินค้าทีหนึ่ง = ยิง SAP หนึ่งครั้ง (ผ่าน /materials/{id}/stock)
   * คนเดินดูสิบหน้าก็สิบครั้ง ทั้งที่ ETL ดึงมาเก็บไว้ให้ทุกชั่วโมงอยู่แล้ว
   * ตัวเลขชุดเดียวกับที่การ์ดในหน้ารายการและตะกร้าใช้ จึงไม่มีทางขัดกันเองด้วย
   * (ยอดสดจริงยืนยันอีกทีตอนเช็คทั้งบิลก่อนออกใบเสนอราคา ซึ่งเป็นจังหวะที่สำคัญจริง)
   */
  const [qty, setQty] = useState(1);
  const [shot, setShot] = useState(0);  // รูปที่กำลังดูอยู่ในแกลเลอรี
  const stripRef = useRef<HTMLDivElement | null>(null);
  const [mode, setMode] = useState<SupplyMode>("ship");
  const [adding, setAdding] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [wished, setWished] = useState(false);
  const [liked, setLiked] = useState<MaterialCard[]>([]);
  const [relCat, setRelCat] = useState<string | null>(null);
  const [feed, setFeed] = useState<MaterialCard[]>([]);
  const [feedBusy, setFeedBusy] = useState(false);
  const [feedEnd, setFeedEnd] = useState(false);
  // ตำแหน่งที่ดึงค้างไว้ (แหล่งที่เท่าไร · ข้ามไปกี่ตัวแล้ว) กับรายการที่เคยเห็น
  // เก็บเป็น ref ไม่ใช่ state เพราะ loadMore ต้องอ่าน/เขียนค่าล่าสุดกลางลูป async
  const cursor = useRef({ src: 0, offset: 0 });
  const seen = useRef<Set<string>>(new Set());
  const sentinel = useRef<HTMLDivElement | null>(null);
  const isStaff = auth.role === "sales" || auth.role === "manager" || auth.role === "admin";

  // เปลี่ยนสินค้า (กดสี/ขนาด) ต้องกลับไปรูปแรกเสมอ ไม่งั้นค้างที่รูปที่ 5 ของตัวเก่า
  // ซึ่งตัวใหม่อาจมีรูปไม่ถึง แล้วจะขึ้นเป็นกรอบว่าง
  useEffect(() => { setShot(0); }, [matnr]);

  // เลื่อนรูปย่อยที่กำลังเลือกให้อยู่ในสายตาเสมอ — กดลูกศรบนรูปใหญ่แล้วแถบข้างล่างต้องตามด้วย
  // ไม่งั้นพอเลื่อนไปรูปที่ 8 แถบยังค้างอยู่รูปที่ 1 มองไม่ออกว่าตอนนี้อยู่ตรงไหน
  useEffect(() => {
    const el = stripRef.current?.children[shot] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [shot]);

  // ดึงรูปถัดไป/ก่อนหน้ามาไว้ในแคชล่วงหน้า — กดลูกศรแล้วรูปขึ้นทันที ไม่ต้องรอโหลดใหม่ทุกครั้ง
  // อ่านจาก item ตรงๆ ไม่ใช้ตัวแปร shots เพราะ shots ประกาศหลังจุดนี้ (hook ต้องอยู่เหนือ early return)
  useEffect(() => {
    const list = item?.images ?? [];
    if (list.length < 2) return;
    for (const i of [shot + 1, shot - 1]) {
      const u = list[(i + list.length) % list.length];
      if (u) new Image().src = normalizeImageUrl(u);
    }
  }, [shot, item]);

  useEffect(() => {
    setItem(null);
    setError(null);
    setQty(1);
    setLiked([]);
    setFeed([]);
    setRelCat(null);
    window.scrollTo({ top: 0 }); // กดสินค้าที่เกี่ยวข้องแล้วต้องขึ้นต้นหน้าใหม่ ไม่ใช่ค้างอยู่กลางหน้า
    apiGet<MaterialDetail>(`/materials/${matnr}`)
      .then((m) => {
        setItem(m);
        setMode(m.requires_install ? "install" : plant && m.is_takeaway_ok ? "takeaway" : "ship");
        setRelCat(m.category_id);
      })
      .catch((e) => setError(errorMessage(e)));
  }, [matnr, auth.user?.id]);

  // "คุณอาจจะชอบ" = ของขายดีจากแบรนด์เดียวกัน (ไม่มีแบรนด์ก็เอาห้องเดียวกัน) เอาเฉพาะตัวที่มีรูป
  // แถวนี้ดึงครั้งเดียวต่อสินค้า ไม่มีเลื่อนหน้า — เป็นแค่แถวแนะนำ
  useEffect(() => {
    if (!item) return;
    const key = item.brand_id ? `brand=${encodeURIComponent(item.brand_id)}` : item.room ? `room=${encodeURIComponent(item.room)}` : item.category_id ? `category=${encodeURIComponent(item.category_id)}` : null;
    if (!key) return;
    let alive = true;
    apiGet<SearchOut>(`/materials/search?${key}&has_image=true&sort=bestseller&limit=16`)
      .then((r) => alive && setLiked(r.items.filter((x) => x.matnr !== item.matnr).slice(0, 12)))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [item?.matnr, auth.user?.id]);

  /** ลำดับแหล่งของฟีด "สินค้าที่เกี่ยวข้อง" — ไล่ลงไปเรื่อยๆ จนกว่าจะหมดทุกแหล่ง
   *
   * ใกล้ตัวที่สุดมาก่อน แล้วค่อยกว้างออก: หมวดที่เลือก → หมวดพี่น้อง → หมวดของที่อยู่ในตะกร้า
   * → แบรนด์เดียวกัน → ห้องเดียวกัน → ขายดีทั้งร้าน
   *
   * ของในตะกร้าอยู่ในลิสต์ด้วยเพราะตอนหมวดนี้หมด สิ่งที่ลูกค้ากำลังเล็งอยู่จริงๆ คือของที่เขา
   * หยิบใส่ตะกร้าไว้แล้ว — เดาจากตรงนั้นแม่นกว่าโยนของขายดีทั้งร้านใส่หน้าเขา
   */
  const cartCats = (cart.cart?.items || []).map((i) => i.category_id).filter(Boolean).join(",");
  const sources = useMemo(() => {
    if (!item) return [] as { key: string; query: string }[];
    const out: { key: string; query: string }[] = [];
    const keys = new Set<string>();
    const push = (key: string, query: string) => {
      if (keys.has(key)) return;
      keys.add(key);
      out.push({ key, query });
    };
    if (relCat) push(`cat:${relCat}`, `category=${encodeURIComponent(relCat)}`);
    for (const c of item.related_categories) push(`cat:${c.id}`, `category=${encodeURIComponent(c.id)}`);
    for (const id of cartCats.split(",").filter(Boolean)) push(`cat:${id}`, `category=${encodeURIComponent(id)}`);
    if (item.brand_id) push(`brand:${item.brand_id}`, `brand=${encodeURIComponent(item.brand_id)}`);
    if (item.room) push(`room:${item.room}`, `room=${encodeURIComponent(item.room)}`);
    push("all", "sort=bestseller");
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- related_categories เปลี่ยนพร้อม matnr เสมอ
  }, [item?.matnr, relCat, cartCats]);

  // เปลี่ยนสินค้า/สลับชิปหมวด = เริ่มฟีดใหม่ทั้งหมด
  useEffect(() => {
    if (!item) return;
    cursor.current = { src: 0, offset: 0 };
    seen.current = new Set([item.matnr]); // ตัวที่กำลังดูอยู่ไม่ต้องโผล่ในฟีดของตัวเอง
    setFeed([]);
    setFeedEnd(false);
  }, [item?.matnr, relCat]);

  const loadMore = useCallback(async () => {
    if (feedBusy || feedEnd || !sources.length) return;
    setFeedBusy(true);
    try {
      let added = 0;
      let hops = 0;
      // ขอจนได้ของใหม่ครบหนึ่งหน้า — แหล่งหนึ่งอาจคืนแต่ของที่โชว์ไปแล้ว ต้องข้ามไปแหล่งถัดไป
      // ไม่งั้นจะได้กริดที่โตทีละ 2-3 ตัวแล้วหยุด ทั้งที่ยังมีของให้ดูอีกเยอะ
      while (added < FEED_PAGE && cursor.current.src < sources.length && hops < FEED_MAX_HOPS) {
        hops += 1;
        const s = sources[cursor.current.src];
        const r = await apiGet<SearchOut>(
          `/materials/search?${s.query}&has_image=true&limit=${FEED_PAGE}&offset=${cursor.current.offset}`,
        );
        if (!r.items.length || cursor.current.offset + r.items.length >= r.total) {
          cursor.current = { src: cursor.current.src + 1, offset: 0 }; // แหล่งนี้หมดแล้ว
        } else {
          cursor.current = { ...cursor.current, offset: cursor.current.offset + r.items.length };
        }
        const fresh = r.items.filter((x) => !seen.current.has(x.matnr));
        fresh.forEach((x) => seen.current.add(x.matnr));
        if (fresh.length) setFeed((prev) => [...prev, ...fresh]);
        added += fresh.length;
      }
      if (cursor.current.src >= sources.length) setFeedEnd(true);
    } catch {
      /* เลื่อนขึ้นลงใหม่แล้วลองอีกรอบได้ ไม่ต้องขึ้น error ทั้งหน้า */
    } finally {
      setFeedBusy(false);
    }
  }, [feedBusy, feedEnd, sources]);

  /** โหลดเพิ่มเองเมื่อเลื่อนใกล้ถึงท้ายกริด
   *
   * rootMargin กว้าง 800px = เริ่มโหลดตั้งแต่ยังเลื่อนไม่ถึง ของชุดถัดไปจึงมาถึงก่อนที่ลูกค้า
   * จะเห็นที่ว่าง (รูปในการ์ดเป็น loading="lazy" อยู่แล้ว จึงไม่ได้ดึงรูปทั้งหมดพร้อมกัน)
   *
   * feed.length อยู่ใน deps ตั้งใจ — observer ไม่ยิงซ้ำถ้าจุดสังเกตยังค้างอยู่ในจอเหมือนเดิม
   * สร้างใหม่หลังต่อของทุกครั้งจึงเป็นวิธีให้มันเช็คอีกทีว่ายังต้องโหลดต่อไหม
   */
  useEffect(() => {
    const el = sentinel.current;
    if (!el || feedEnd) return;
    const io = new IntersectionObserver((es) => es[0]?.isIntersecting && void loadMore(), { rootMargin: "800px" });
    io.observe(el);
    return () => io.disconnect();
  }, [loadMore, feedEnd, feed.length]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    setWished(false);
    if (!auth.user || !matnr) return;
    apiGet<{ matnr: string }[]>("/me/wishlist").then((ws) => setWished(ws.some((w) => w.matnr === matnr))).catch(() => setWished(false));
  }, [auth.user, matnr]);

  const toggleWish = async () => {
    if (!auth.user) return auth.openLogin();
    const r = await apiPost<{ in_wishlist: boolean }>(`/me/wishlist/${matnr}`);
    setWished(r.in_wishlist);
    setToast(r.in_wishlist ? "เก็บใส่รายการโปรดแล้ว" : "เอาออกจากรายการโปรดแล้ว");
  };

  /** เซลล์กดจากหน้าสินค้าได้เลย ไม่ต้องกลับไปค้น MATNR ซ้ำในหน้าตะกร้าที่ดูแล */
  const addToSalesCart = async () => {
    if (!item) return;
    setAdding(true);
    try {
      const id = sales.activeId || (await sales.openCart()).id;
      const use = fit(item, mode);
      await sales.addItem(item.matnr, qty, use, use === "takeaway" ? plant?.plant_code || null : null, id);
      setToast(`เพิ่ม ${item.name_th} × ${qty} ลงตะกร้าที่ดูแลแล้ว — เช็คสต็อกได้ที่หน้าตะกร้า`);
    } catch (e) {
      setToast("เพิ่มไม่สำเร็จ: " + errorMessage(e));
    } finally {
      setAdding(false);
    }
  };

  // ลงตะกร้าได้ทุกตัวเสมอ — ถ้าวิธีที่ค้างไว้ใช้กับสินค้านี้ไม่ได้ (ยังไม่ได้เลือกสาขา / ตัวนี้ต้องให้ช่างติดตั้ง)
  // ก็ตกไปใช้วิธีที่ใช้ได้แทน แทนที่จะปิดปุ่มจนลูกค้าซื้อไม่ได้ · "จัดส่ง + ติดตั้ง" ใช้ได้กับทุกตัว
  const fit = (m: MaterialDetail, want: SupplyMode): SupplyMode => {
    if (want === "takeaway" && (!m.is_takeaway_ok || !plant)) return m.requires_install ? "install" : "ship";
    if (want === "ship" && m.requires_install) return "install";
    return want;
  };

  const addToCart = async (thenBuy = false) => {
    if (!item) return;
    const use = fit(item, mode);
    setAdding(true);
    try {
      await cart.add(item.matnr, { qty, supply_mode: use, plant_code: use === "takeaway" || use === "pickup" ? plant?.plant_code || null : null });
      if (thenBuy) return nav("/cart");
      setToast(`เพิ่ม ${item.name_th} × ${qty} ลงตะกร้าแล้ว`);
    } catch (e) {
      setToast("เพิ่มไม่สำเร็จ: " + errorMessage(e));
    } finally {
      setAdding(false);
    }
  };

  if (error) return <main className="container sec"><div className="note err">{error}</div></main>;
  if (!item) return <main className="container sec"><div className="ph" style={{ height: 420 }}>กำลังโหลดสินค้า…</div></main>;

  // rows ของลูกค้าถูกกรองเหลือเฉพาะสาขาที่เลือกมาแล้วจากฝั่ง API
  const inStoreQty = plant ? (item?.stock_sites || []).find((s) => s.plant_code === plant.plant_code)?.qty ?? 0 : 0;
  // สถานะของจาก product_stock — กติกาเดียวกับการ์ดในหน้ารายการสินค้า
  const stChecked = !!item?.stock;
  const stReady = item?.stock?.ready_qty ?? 0;
  const stLater = item?.stock?.later_qty ?? 0;
  const stMadeToOrder = !!item?.stock?.made_to_order;
  const stPreOrder = stChecked && stReady <= 0 && (stLater > 0 || stMadeToOrder);
  const stSoldOut = stChecked && stReady <= 0 && stLater <= 0 && !stMadeToOrder;
  const stLow = stChecked && stReady > 0 && stReady <= 5;
  const size = sizeText(item.spec);
  // แกลเลอรีรูปจริงของสินค้าตัวนี้ · ว่างเมื่อยังไม่ได้ดึงรูปมา แล้วค่อยตกไปใช้รูปหลักใบเดียว
  const shots = item.images ?? [];
  // เลื่อนทีละ ~3 ใบ ไม่ใช่ทีละใบ — กดทีเดียวเห็นชุดใหม่ ไม่ต้องกดรัว
  // ตั้ง scrollLeft ตรงๆ ไม่ใช้ scrollBy({behavior:"smooth"}) เพราะบางเบราว์เซอร์ไม่ขยับเลย
  // (เจอกับตัว) ส่วนความลื่นได้จาก CSS scroll-behavior อยู่แล้ว ที่ไหนไม่รองรับก็แค่กระโดดไปเลย
  const scrollStrip = (dir: number) => {
    const el = stripRef.current;
    if (el) el.scrollLeft += dir * 260;
  };
  const sibs = item.related_categories;

  return (
    <main className="container sec product">
      <nav className="crumbs small muted">
        <Link to="/">หน้าแรก</Link> › {item.category_id && <><Link to={`/search?category=${item.category_id}`}>{item.category_name}</Link> › </>}<span>{item.name_th}</span>
      </nav>
      <div className="product-grid">
        <div className="product-gallery">
          <div className="gallery-main">
            <Placeholder src={shots.length ? [normalizeImageUrl(shots[shot])] : imageSources(item.matnr, item.image_url)}
                         alt={item.name_th} priority label={<>PRODUCT SHOT<br />1:1 · 1200 × 1200</>} />
            {/* ปุ่มเลื่อนรูป — โชว์เมื่อมีมากกว่าหนึ่งใบ วนกลับหัวท้ายได้ ไม่ต้องกดย้อนยาว */}
            {shots.length > 1 && (
              <>
                <button className="gallery-nav prev" onClick={() => setShot((i) => (i - 1 + shots.length) % shots.length)} aria-label="รูปก่อนหน้า">
                  <Icon name="chevron_left" size={22} />
                </button>
                <button className="gallery-nav next" onClick={() => setShot((i) => (i + 1) % shots.length)} aria-label="รูปถัดไป">
                  <Icon name="chevron_right" size={22} />
                </button>
                <span className="gallery-count">{shot + 1}/{shots.length}</span>
              </>
            )}
            <button className={"gallery-wish" + (wished ? " on" : "")} onClick={toggleWish} aria-label="รายการโปรด" title={wished ? "เอาออกจากรายการโปรด" : "เก็บใส่รายการโปรด"}>
              <Icon name="favorite" size={20} fill={wished} />
            </button>
          </div>
          {/* แถวรูปย่อย = รูปจริงของสินค้าตัวนี้ (ตาราง material_images) ไม่ใช่รูปของสีอื่นแบบเดิม
              แถวเดียวเลื่อนซ้ายขวา — รูปมีได้ถึง 24 ใบ ถ้าปล่อยให้ตกบรรทัดจะดันเนื้อหาข้างล่างหายไปทั้งจอ */}
          {shots.length > 1 && (
            <div className="thumb-strip">
              <button className="strip-nav" onClick={() => scrollStrip(-1)} aria-label="เลื่อนรูปย่อยไปทางซ้าย">
                <Icon name="chevron_left" size={18} />
              </button>
              <div className="thumbs" ref={stripRef}>
                {shots.map((u, i) => (
                  <button key={u} className={i === shot ? "on" : ""} onClick={() => setShot(i)} aria-label={`รูปที่ ${i + 1}`}>
                    <Placeholder src={[normalizeImageUrl(u)]} alt={`${item.name_th} รูปที่ ${i + 1}`} label="" />
                  </button>
                ))}
              </div>
              <button className="strip-nav" onClick={() => scrollStrip(1)} aria-label="เลื่อนรูปย่อยไปทางขวา">
                <Icon name="chevron_right" size={18} />
              </button>
            </div>
          )}
        </div>

        <div className="product-info">
          <h1>{item.name_th}</h1>
          <div className="product-meta small">
            <span>แบรนด์ <Link to={`/search?brand=${item.brand_id ?? ""}`} className="strong">{item.brand_name || "SB DESIGN"}</Link></span>
            <span className="sep">|</span>
            {/* เลขเดียวพอ — SKU กับ MATNR เป็นเลขเดียวกันเกือบทั้งฐาน โชว์สองอันมีแต่ทำให้สับสน */}
            <span className="mono">MATNR {item.matnr}</span>
          </div>
          <div className="product-meta small muted">
            {item.variant && <span>รุ่น {item.variant}</span>}
            {size && <><span className="sep">|</span><span>{size}</span></>}
            {item.sold_qty > 0 && <><span className="sep">|</span><span>ขายแล้ว {num(item.sold_qty)} ชิ้น</span></>}
          </div>

          <div className="product-price">
            <span className="now">{baht(item.price)}</span>
            {item.compare_at_price && <span className="was">{baht(item.compare_at_price)}</span>}
            {item.discount_percent ? <span className="chip red">-{item.discount_percent}%</span> : null}
          </div>
          {auth.user ? null : (
            <div className="note">เข้าสู่ระบบเพื่อสะสมพ้อยท์และชำระเงินได้ทันที <button className="link-btn" onClick={auth.openLogin}>เข้าสู่ระบบ</button></div>
          )}
          {num(item.price) >= 10000 && <div className="small muted" style={{ marginTop: 6 }}>ผ่อน 0% นาน 10 เดือน · บัตรที่ร่วมรายการ</div>}

          {/* ของตัวโชว์/ฝากขาย — บอกเงื่อนไขตั้งแต่หน้าสินค้า ไม่ใช่ให้ไปรู้ตอนจ่ายเงินหรือตอนอยากคืน */}
          {item.pickup_only && (
            <div className="pickup-terms">
              <div className="row" style={{ gap: 6 }}><Icon name="storefront" size={18} /> <b>ซื้อได้ที่สาขาเท่านั้น</b></div>
              <div className="row" style={{ gap: 6 }}><Icon name="block" size={18} /> <b>ซื้อแล้วไม่รับเปลี่ยนหรือคืน</b></div>
              <p className="small">
                เป็นสินค้าจัดแสดงหน้าร้าน มีชิ้นเดียวและอาจมีร่องรอยจากการโชว์ —
                กรุณาตรวจสภาพสินค้าที่สาขาก่อนตัดสินใจซื้อ
              </p>
            </div>
          )}

          {!isStaff && (
            <div className="stock-line">
              {/* จำนวนของมาจาก product_stock เหมือนหน้ารายการสินค้า — ยอดสดยืนยันตอนสั่งซื้อ */}
              {stChecked ? (
                stSoldOut ? (
                  <b className="amber">สินค้าหมด</b>
                ) : stPreOrder ? (
                  <b className="amber">พรีออเดอร์</b>
                ) : (
                  <b className={stLow ? "red" : ""}>มีสต็อก {stReady} ชิ้น</b>
                )
              ) : (
                <b>มีสต็อก - ชิ้น</b>
              )}
              {stReady > 0 && <><span className="sep">|</span><span><Icon name="local_shipping" size={16} /> พร้อมจัดส่ง</span></>}
              {item.stock?.later_date && <><span className="sep">|</span><span>ของเข้าเพิ่ม {thDate(item.stock.later_date)}</span></>}
              {inStoreQty > 0 && plant && <><span className="sep">|</span><span><Icon name="storefront" size={16} /> {plant.name} มี {inStoreQty} ชิ้น</span></>}
            </div>
          )}

          {/* สาขาที่มีของให้ไปดูของจริงได้ — มาจาก STOCK_ON_SITES ของ SAP (ไม่รวมคลัง/ระดับบริษัท)
              สำคัญกับสินค้าตัวโชว์เป็นพิเศษ: ของมีชิ้นเดียวต่อสาขา ลูกค้าต้องรู้ว่าไปดูที่ไหนได้ */}
          {item.stock_sites.length > 0 && (
            <details className="site-stock" open={item.stock_sites.length <= 6}>
              <summary>
                <Icon name="storefront" size={16} /> มีของที่ {item.stock_sites.length} สาขา
              </summary>
              <ul>
                {item.stock_sites.map((st) => (
                  <li key={st.plant_code}>
                    <span>{st.name}</span>
                    <b>{st.qty} ชิ้น</b>
                  </li>
                ))}
              </ul>
              <p className="tiny muted">ยอดนี้อัปเดตเป็นรอบ — โทรเช็คกับสาขาก่อนเดินทางไปดูของ</p>
            </details>
          )}

          {/* ตัวโชว์มีรอย/สีจริงต่างกันแต่ละสาขา — พนักงานถ่ายของจริงในสาขาตัวเองเก็บไว้ (ลูกค้าไม่เห็นส่วนนี้)
              วางต่อจากรายชื่อสาขาที่มีของ เพราะเป็นเรื่องเดียวกัน: ของชิ้นนี้อยู่ที่ไหน หน้าตาจริงเป็นยังไง */}
          {item.is_display && <BranchPhotos matnr={item.matnr} />}
          {isStaff && item.is_display && <StaffPhotos matnr={item.matnr} />}

          {/* ต้นทางแยกทุกสีเป็นคนละ MATNR — กดสีอื่นคือเปลี่ยนหน้าสินค้า ไม่ใช่เปลี่ยนตัวเลือกในหน้าเดิม */}
          {item.colors.length > 1 && (
            <div className="colors">
              <b className="small">เลือกสี: <span className="muted">{item.color}</span></b>
              <div className="color-list">
                {item.colors.map((c) => (
                  <Link key={c.matnr} to={`/p/${c.matnr}`} className={"color-opt" + (c.matnr === item.matnr ? " on" : "")}>
                    <Placeholder src={imageSources(c.matnr, c.image_url)} alt={c.label} label={c.label} />
                    <small>{c.label}</small>
                  </Link>
                ))}
              </div>
            </div>
          )}

          {/* แกนขนาด — คนละแกนกับสี กดเลือกขนาดแล้วระบบพยายามคงสีเดิมไว้ (ดู variant_axes ฝั่งหลังบ้าน)
              เป็นปุ่มตัวหนังสือ ไม่ใช่รูป เพราะขนาดดูจากรูปไม่ออก ต้องอ่านตัวเลข */}
          {item.sizes.length > 1 && (
            <div className="sizes">
              <b className="small">เลือกขนาด:</b>
              <div className="size-list">
                {item.sizes.map((z) => (
                  <Link key={z.matnr} to={`/p/${z.matnr}`} className={"size-opt" + (z.matnr === item.matnr ? " on" : "")}>
                    {z.label}
                  </Link>
                ))}
              </div>
            </div>
          )}

          <ul className="product-flags">
            <li><Icon name={item.is_takeaway_ok ? "shopping_bag" : "local_shipping"} size={18} /> {item.is_takeaway_ok ? "ยกกลับได้จากสาขา" : "จัดส่งจากคลังเท่านั้น"}</li>
            {/* โชว์เฉพาะตอนที่ต้องใช้ช่าง — "ไม่ต้องติดตั้ง" เป็นค่าปกติของสินค้าส่วนใหญ่
                บอกไปก็ไม่ได้ช่วยตัดสินใจ มีแต่ทำให้บรรทัดที่ต้องรู้จริงๆ จมหายไป */}
            {item.requires_install && <li><Icon name="handyman" size={18} /> ต้องติดตั้งโดยช่าง (มีค่าติดตั้ง)</li>}
            {item.weight_kg && <li><Icon name="scale" size={18} /> น้ำหนัก {num(item.weight_kg)} กก. · ปริมาตร {num(item.volume_m3)} ลบ.ม.</li>}
          </ul>

          {sales.enabled ? (
            <div className="add-box">
              <div className="product-actions">
                <div className="qty">
                  <button onClick={() => setQty(Math.max(1, qty - 1))} disabled={qty <= 1} aria-label="ลด"><Icon name="remove" size={18} /></button>
                  <span>{qty}</span>
                  <button onClick={() => setQty(qty + 1)} aria-label="เพิ่ม"><Icon name="add" size={18} /></button>
                </div>
                <button className="btn primary lg grow" onClick={addToSalesCart} disabled={adding}>
                  <Icon name="add_shopping_cart" size={20} /> {adding ? "กำลังเพิ่ม…" : sales.activeId ? "เพิ่มลงตะกร้าที่ดูแล" : "เปิดตะกร้าใหม่แล้วเพิ่ม"}
                </button>
              </div>
              <p className="small muted" style={{ marginTop: 6 }}>
                {sales.active?.customer ? `ตะกร้าของ ${sales.active.customer.name}` : sales.activeId ? `ตะกร้า ${sales.active?.no || ""} · ยังไม่ผูกลูกค้า` : "ยังไม่มีตะกร้าที่ดูแล — กดปุ่มแล้วระบบเปิดให้เอง"}
                {" · "}<Link to="/sales" className="strong">ไปหน้าตะกร้าที่กำลังดูแล</Link> เพื่อเช็คสต็อกและออกใบเสนอราคา
              </p>
            </div>
          ) : isStaff ? (
            <div className="note">โหมดพนักงาน: เพิ่มสินค้าให้ลูกค้าได้จากหน้า <Link to="/sales" className="strong">ตะกร้าที่กำลังดูแล</Link> (ค้นหา MATNR → ลงตะกร้า)</div>
          ) : (
            <div className="add-box">
              {/* วิธีรับสินค้า (ยกกลับ/ส่ง/ติดตั้ง) ไปเลือกในตะกร้า — ตรงนี้เอาให้กดซื้อได้เร็วที่สุด */}
              <div className="product-actions">
                <div className="qty">
                  <button onClick={() => setQty(Math.max(1, qty - 1))} disabled={qty <= 1} aria-label="ลด"><Icon name="remove" size={18} /></button>
                  <span>{qty}</span>
                  <button onClick={() => setQty(qty + 1)} aria-label="เพิ่ม"><Icon name="add" size={18} /></button>
                </div>
                <button className="btn lg grow" onClick={() => addToCart()} disabled={adding}>
                  <Icon name="add_shopping_cart" size={20} /> {adding ? "กำลังเพิ่ม…" : "เพิ่มลงตะกร้า"}
                </button>
                <button className="btn primary lg grow" onClick={() => addToCart(true)} disabled={adding}>ซื้อเลย</button>
              </div>
            </div>
          )}
          <p className="small muted" style={{ marginTop: 6 }}>
            {plant ? `สาขาที่เลือก: ${plant.name}` : "ยังไม่ได้เลือกสาขา (เลือกได้ที่ “รับที่สาขา” ด้านบน)"}
          </p>

          {/* สี่หัวข้อนี้คือชุดเดียวกับที่ลูกค้าเห็นบน sbdesignsquare.com — เปิดหัวข้อแรกไว้ ที่เหลือพับ */}
          <div className="product-accs">
            <Acc title="ข้อมูลสินค้า" open>
              {item.description ? <p>{item.description}</p> : <p className="muted">ยังไม่มีคำอธิบายจากต้นทางสำหรับสินค้าตัวนี้ · ดูรายละเอียดที่หัวข้อ “คุณสมบัติ” ด้านล่าง</p>}
            </Acc>

            <Acc title="คุณสมบัติ">
              <div className="specs">
                <SpecRow label="รหัสสินค้า (MATNR)" value={<span className="mono">{item.matnr}</span>} />
                {item.barcode &&<SpecRow label="บาร์โค้ด" value={<span className="mono">{item.barcode}</span>} />}
                <SpecRow label="แบรนด์" value={item.brand_name || "SB DESIGN"} />
                {item.variant && <SpecRow label="รุ่น / ซีรีส์" value={item.variant} />}
                {item.category_name && <SpecRow label="หมวดสินค้า" value={<Link to={`/search?category=${item.category_id}`}>{item.category_name}</Link>} />}
                {size && <SpecRow label="ขนาด" value={size} />}
                {item.color && <SpecRow label="สี" value={item.color} />}
                {item.style && <SpecRow label="สไตล์" value={item.style} />}
                {item.weight_kg && <SpecRow label="น้ำหนัก" value={`${num(item.weight_kg)} กก.`} />}
                {item.volume_m3 && <SpecRow label="ปริมาตรบรรจุ" value={`${num(item.volume_m3)} ลบ.ม.`} />}
                {item.requires_install && <SpecRow label="การประกอบ" value="ต้องติดตั้งโดยช่าง (มีค่าบริการ)" />}
                <SpecRow label="ยกกลับจากสาขา" value={item.is_takeaway_ok ? "ได้ (ถ้าสาขามีของ)" : "ไม่ได้ · จัดส่งจากคลังเท่านั้น"} />
                {item.name_en && <SpecRow label="ชื่อภาษาอังกฤษ" value={item.name_en} />}
              </div>
              <p className="small muted" style={{ marginTop: 8 }}>ข้อมูลอัปเดตล่าสุด {thDate(item.synced_at)}</p>
            </Acc>

            <Acc title="การรับประกัน">
              <ul className="bullets">
                <li>รับประกันความเสียหายจากการผลิตและวัสดุ ตามเงื่อนไขการรับประกันของ SB Design Square นับจากวันที่รับสินค้า</li>
                <li>ไม่ครอบคลุมการใช้งานผิดประเภท การดัดแปลง อุบัติเหตุ หรือการสึกหรอตามอายุการใช้งานปกติ</li>
                <li>แจ้งเคลมได้ที่สาขาที่ซื้อหรือฝ่ายบริการลูกค้า โดยแจ้งรหัสสินค้า <span className="mono">{item.matnr}</span> พร้อมใบเสร็จ/ใบกำกับภาษี</li>
                {item.requires_install && <li>งานติดตั้งโดยช่างของบริษัทอยู่ในความดูแลของทีมบริการหลังการขาย</li>}
              </ul>
            </Acc>

            <Acc title="การจัดส่ง">
              <ul className="bullets">
                <li>{item.is_takeaway_ok ? "ยกกลับเองได้จากสาขาที่มีของ — ไม่มีค่าจัดส่ง" : "สินค้าชิ้นนี้จัดส่งจากคลังเท่านั้น ยกกลับจากสาขาไม่ได้"}</li>
                <li>ค่าจัดส่งคิดตามเขตพื้นที่ปลายทาง ระบบจะคำนวณให้ตอนกรอกที่อยู่ในหน้าชำระเงิน</li>
                <li>{item.requires_install ? "ต้องติดตั้งโดยช่าง — ทีมงานจะติดต่อนัดวันติดตั้งหลังยืนยันคำสั่งซื้อ" : "ไม่ต้องใช้ช่างติดตั้ง เลือกให้ช่างประกอบเพิ่มได้ (มีค่าบริการ)"}</li>
                {item.stock?.later_date && <li>รอบของเข้าเพิ่มจากข้อมูลล่าสุด: {thDate(item.stock.later_date)}</li>}
                <li>เลือกวันและช่วงเวลาจัดส่งได้ในหน้าชำระเงิน</li>
              </ul>
            </Acc>
          </div>
        </div>
      </div>

      {/* คำบรรยายเต็ม (LONG_DESC) — วางเป็นบล็อกกว้างเต็มใต้ส่วนบน เหมือนหน้าสินค้าของเว็บจริง
          ไม่ยัดลงในกล่อง "ข้อมูลสินค้า" เพราะข้อความยาวกว่าช่องขวามาก อ่านในคอลัมน์แคบแล้วอึดอัด
          เนื้อหาถูกล้าง script/style ตั้งแต่ตอน import แล้ว (ดู etl/html_clean.py) */}
      {item.description_long && (
        <section className="product-long">
          <div dangerouslySetInnerHTML={{ __html: item.description_long }} />
        </section>
      )}

      {/* แถวแนะนำแถวเดียว — ของขายดีจากแบรนด์/ห้องเดียวกัน */}
      <div className="sec-gap">
        <ProductRow title="สินค้าที่คุณอาจจะชอบ" items={liked} more={item.brand_id ? `/search?brand=${item.brand_id}` : undefined} />
      </div>

      {/* ที่เกี่ยวข้อง: หมวดเดียวกันก่อน แล้วสลับไปหมวดพี่น้อง (เตียง → ชุดเตียง/หัวเตียง ฯลฯ) ได้จากชิป
          สีอื่นของรุ่นเดียวกันเป็นคนละ MATNR ก็ขึ้นอยู่ในนี้เองเพราะอยู่หมวดเดียวกัน */}
      {relCat && (
        <section className="related sec-gap">
          <div className="sec-head">
            <h2>สินค้าที่เกี่ยวข้อง</h2>
            <Link to={`/search?category=${relCat}`} className="sec-more">ดูทั้งหมด</Link>
          </div>
          {sibs.length > 1 && (
            <div className="chips-row">
              {sibs.map((c) => (
                <button key={c.id} className={"chip-btn" + (c.id === relCat ? " on" : "")} onClick={() => setRelCat(c.id)}>{c.name_th}</button>
              ))}
            </div>
          )}
          <div className="pgrid">
            {feed.map((r) => (
              <ProductCard key={r.matnr} item={r} />
            ))}
          </div>

          {/* จุดสังเกตท้ายกริด — เลื่อนมาใกล้เมื่อไหร่ก็โหลดชุดถัดไปเอง ไม่ต้องกดปุ่ม
              ให้ความสูงไว้เผื่อ: เบราว์เซอร์บางตัวไม่รายงานอิลิเมนต์ที่พื้นที่เป็นศูนย์ */}
          <div ref={sentinel} style={{ height: 24 }} aria-hidden />

          {feedBusy && (
            <div className="pgrid feed-skeleton" aria-hidden>
              {Array.from({ length: 4 }, (_, i) => <div key={i} className="ph" style={{ aspectRatio: "3 / 4", borderRadius: 12 }} />)}
            </div>
          )}
          {!feedBusy && !feed.length && feedEnd && <div className="note">ยังไม่มีสินค้าอื่นในหมวดนี้</div>}
          {!feedBusy && feed.length > 0 && feedEnd && <p className="center small muted" style={{ marginTop: 16 }}>ดูครบทุกรายการแล้ว</p>}
        </section>
      )}

      {toast && (
        <div className="toast" role="status">
          <Icon name="check_circle" size={20} /> {toast} <Link to="/cart">ดูตะกร้า</Link>
        </div>
      )}
    </main>
  );
}
