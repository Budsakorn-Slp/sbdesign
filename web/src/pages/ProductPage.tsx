import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import Icon from "../components/Icon";
import Placeholder from "../components/Placeholder";
import ProductCard from "../components/ProductCard";
import ProductRow from "../components/ProductRow";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useCart } from "../lib/cart";
import { useContent } from "../lib/content";
import { baht, num, thDate } from "../lib/format";
import { useSales } from "../lib/sales";
import type { MaterialCard, MaterialDetail, SearchOut, StockOut, SupplyMode } from "../lib/types";

const REL_PAGE = 24;

/** "167.5X40X75" → "กว้าง 167.5 × ลึก 40 × สูง 75 ซม." — ต้นทางเก็บเป็นสตริงเดียว (GROES) */
function sizeText(spec: string | null): string | null {
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
  const [stock, setStock] = useState<StockOut | null>(null);
  const [qty, setQty] = useState(1);
  const [mode, setMode] = useState<SupplyMode>("ship");
  const [adding, setAdding] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [wished, setWished] = useState(false);
  const [liked, setLiked] = useState<MaterialCard[]>([]);
  const [relCat, setRelCat] = useState<string | null>(null);
  const [rel, setRel] = useState<MaterialCard[]>([]);
  const [relTotal, setRelTotal] = useState(0);
  const [relBusy, setRelBusy] = useState(false);
  const isStaff = auth.role === "sales" || auth.role === "manager" || auth.role === "admin";

  useEffect(() => {
    setItem(null);
    setStock(null);
    setError(null);
    setQty(1);
    setLiked([]);
    setRel([]);
    setRelTotal(0);
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

  // "สินค้าที่เกี่ยวข้อง" = หมวดเดียวกัน (สลับไปหมวดพี่น้องได้ด้วยชิปด้านบน) — เลื่อนดูต่อได้ยาวๆ
  useEffect(() => {
    if (!relCat) return;
    let alive = true;
    setRelBusy(true);
    apiGet<SearchOut>(`/materials/search?category=${encodeURIComponent(relCat)}&has_image=true&limit=${REL_PAGE}`)
      .then((r) => {
        if (!alive) return;
        setRel(r.items);
        setRelTotal(r.total);
      })
      .catch(() => alive && setRel([]))
      .finally(() => alive && setRelBusy(false));
    return () => {
      alive = false;
    };
  }, [relCat, auth.user?.id]);

  const moreRelated = async () => {
    if (!relCat) return;
    setRelBusy(true);
    try {
      const r = await apiGet<SearchOut>(`/materials/search?category=${encodeURIComponent(relCat)}&has_image=true&limit=${REL_PAGE}&offset=${rel.length}`);
      setRel((prev) => [...prev, ...r.items.filter((x) => !prev.some((p) => p.matnr === x.matnr))]);
      setRelTotal(r.total);
    } catch {
      /* กดใหม่ได้ ไม่ต้องขึ้น error ทั้งหน้า */
    } finally {
      setRelBusy(false);
    }
  };

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

  // ดึงสต็อกให้เลยตอนเปิดหน้า แล้วโชว์เป็นบรรทัดสถานะใต้ราคา (ลูกค้าไม่ต้องกดเอง)
  useEffect(() => {
    if (!matnr) return;
    let alive = true;
    const qs = plant ? `?plant=${plant.plant_code}` : "";
    apiGet<StockOut>(`/materials/${matnr}/stock${qs}`)
      .then((s) => alive && setStock(s))
      .catch(() => {}); // เช็คไม่ได้ก็แค่ไม่โชว์บรรทัดสถานะ ไม่ต้องขึ้น error ทั้งหน้า
    return () => {
      alive = false;
    };
  }, [matnr, plant?.plant_code]);

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
  const inStoreQty = stock?.rows.reduce((n, r) => n + r.available, 0) ?? 0;
  const size = sizeText(item.spec);
  const sibs = item.related_categories;

  return (
    <main className="container sec product">
      <nav className="crumbs small muted">
        <Link to="/">หน้าแรก</Link> › {item.category_id && <><Link to={`/search?category=${item.category_id}`}>{item.category_name}</Link> › </>}<span>{item.name_th}</span>
      </nav>
      <div className="product-grid">
        <div className="product-gallery">
          <div className="gallery-main">
            <Placeholder src={item.image_url} alt={item.name_th} label={<>PRODUCT SHOT<br />1:1 · 1200 × 1200</>} />
            <button className={"gallery-wish" + (wished ? " on" : "")} onClick={toggleWish} aria-label="รายการโปรด" title={wished ? "เอาออกจากรายการโปรด" : "เก็บใส่รายการโปรด"}>
              <Icon name="favorite" size={20} fill={wished} />
            </button>
          </div>
          {/* รูปสีอื่นของรุ่นเดียวกันใช้เป็นแถวรูปย่อยไปก่อน — ต้นทางยังส่งมาสินค้าละรูปเดียว */}
          {item.colors.length > 1 && (
            <div className="thumbs">
              {item.colors.map((c) => (
                <Link key={c.matnr} to={`/p/${c.matnr}`} className={c.matnr === item.matnr ? "on" : ""} title={c.color || c.name_th}>
                  <Placeholder src={c.image_url} alt={c.name_th} label={c.color || ""} />
                </Link>
              ))}
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
          {item.price_tier !== "standard" ? (
            <div className="note ok">ราคาสมาชิก {item.price_tier} · ราคาปกติ {baht(item.standard_price)}</div>
          ) : auth.user ? null : (
            <div className="note">เข้าสู่ระบบเพื่อดูราคาสมาชิกและโปรเฉพาะสมาชิก <button className="link-btn" onClick={auth.openLogin}>เข้าสู่ระบบ</button></div>
          )}
          {num(item.price) >= 10000 && <div className="small muted" style={{ marginTop: 6 }}>ผ่อน 0% นาน 10 เดือน · บัตรที่ร่วมรายการ</div>}

          {!isStaff && stock && (
            <div className="stock-line">
              <b className={stock.available ? "green" : "amber"}>{stock.available ? "สินค้ามีสต็อก" : "สั่งจอง · รอของเข้า"}</b>
              {stock.available && <><span className="sep">|</span><span><Icon name="local_shipping" size={16} /> พร้อมจัดส่ง</span></>}
              {stock.earliest_atp && <><span className="sep">|</span><span>ส่งได้เร็วสุด {thDate(stock.earliest_atp)}</span></>}
              {inStoreQty > 0 && plant && <><span className="sep">|</span><span><Icon name="storefront" size={16} /> {plant.name} มี {inStoreQty} ชิ้น</span></>}
            </div>
          )}

          {/* ต้นทางแยกทุกสีเป็นคนละ MATNR — กดสีอื่นคือเปลี่ยนหน้าสินค้า ไม่ใช่เปลี่ยนตัวเลือกในหน้าเดิม */}
          {item.colors.length > 1 && (
            <div className="colors">
              <b className="small">เลือกสี: <span className="muted">{item.color}</span></b>
              <div className="color-list">
                {item.colors.map((c) => (
                  <Link key={c.matnr} to={`/p/${c.matnr}`} className={"color-opt" + (c.matnr === item.matnr ? " on" : "")}>
                    <Placeholder src={c.image_url} alt={c.name_th} label={c.color || ""} />
                    <small>{c.color}</small>
                  </Link>
                ))}
              </div>
            </div>
          )}

          <ul className="product-flags">
            <li><Icon name={item.is_takeaway_ok ? "shopping_bag" : "local_shipping"} size={18} /> {item.is_takeaway_ok ? "ยกกลับได้จากสาขา" : "จัดส่งจากคลังเท่านั้น"}</li>
            <li><Icon name="handyman" size={18} /> {item.requires_install ? "ต้องติดตั้งโดยช่าง (มีค่าติดตั้ง)" : "ไม่ต้องติดตั้ง / ประกอบเองได้"}</li>
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
                <SpecRow label="การประกอบ" value={item.requires_install ? "ต้องติดตั้งโดยช่าง (มีค่าบริการ)" : "ประกอบเองได้ / ไม่ต้องติดตั้ง"} />
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
                {stock?.earliest_atp && <li>รอบส่งเร็วสุดจากข้อมูลสต็อกล่าสุด: {thDate(stock.earliest_atp)}</li>}
                <li>เลือกวันและช่วงเวลาจัดส่งได้ในหน้าชำระเงิน</li>
              </ul>
            </Acc>
          </div>
        </div>
      </div>

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
            {rel.filter((r) => r.matnr !== item.matnr).map((r) => (
              <ProductCard key={r.matnr} item={r} />
            ))}
          </div>
          {!rel.length && !relBusy && <div className="note">ยังไม่มีสินค้าอื่นในหมวดนี้</div>}
          {rel.length < relTotal && (
            <div className="center" style={{ marginTop: 16 }}>
              <button className="btn lg" onClick={moreRelated} disabled={relBusy}>
                {relBusy ? "กำลังโหลด…" : `ดูเพิ่ม (เหลืออีก ${num(relTotal - rel.length)} รายการ)`}
              </button>
            </div>
          )}
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
