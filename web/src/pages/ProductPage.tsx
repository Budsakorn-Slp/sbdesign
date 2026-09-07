import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Icon from "../components/Icon";
import Placeholder from "../components/Placeholder";
import { apiGet, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useCart } from "../lib/cart";
import { useContent } from "../lib/content";
import { baht, num, thDate, thTime } from "../lib/format";
import type { MaterialDetail, StockOut, SupplyMode } from "../lib/types";

export default function ProductPage() {
  const { matnr = "" } = useParams();
  const auth = useAuth();
  const cart = useCart();
  const { plant } = useContent();
  const [item, setItem] = useState<MaterialDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stock, setStock] = useState<StockOut | null>(null);
  const [checking, setChecking] = useState(false);
  const [qty, setQty] = useState(1);
  const [mode, setMode] = useState<SupplyMode>("ship");
  const [adding, setAdding] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const isStaff = auth.role === "sales" || auth.role === "manager" || auth.role === "admin";

  useEffect(() => {
    setItem(null);
    setStock(null);
    setError(null);
    apiGet<MaterialDetail>(`/materials/${matnr}`)
      .then((m) => {
        setItem(m);
        setMode(m.requires_install ? "install" : plant && m.is_takeaway_ok ? "takeaway" : "ship");
      })
      .catch((e) => setError(errorMessage(e)));
  }, [matnr, auth.user?.id]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  const checkStock = async () => {
    setChecking(true);
    try {
      const qs = plant ? `?plant=${plant.plant_code}` : "";
      setStock(await apiGet<StockOut>(`/materials/${matnr}/stock${qs}`));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setChecking(false);
    }
  };

  const addToCart = async () => {
    if (!item) return;
    setAdding(true);
    try {
      await cart.add(item.matnr, { qty, supply_mode: mode, plant_code: mode === "takeaway" || mode === "pickup" ? plant?.plant_code || null : null });
      setToast(`เพิ่ม ${item.name_th} × ${qty} ลงตะกร้าแล้ว`);
    } catch (e) {
      setToast("เพิ่มไม่สำเร็จ: " + errorMessage(e));
    } finally {
      setAdding(false);
    }
  };

  if (error) return <main className="container sec"><div className="note err">{error}</div></main>;
  if (!item) return <main className="container sec"><div className="ph" style={{ height: 420 }}>กำลังโหลดสินค้า…</div></main>;

  const modes: { key: SupplyMode; label: string; sub: string; ok: boolean }[] = [
    { key: "takeaway", label: "ยกกลับจากสาขา", sub: plant ? `รับที่ ${plant.name} · ไม่มีค่าส่ง` : "ต้องเลือกสาขาก่อน (รับที่สาขา ด้านบน)", ok: item.is_takeaway_ok && !!plant },
    { key: "ship", label: "จัดส่งถึงบ้าน", sub: "จากคลัง · คิดค่าส่งตามเขต", ok: !item.requires_install },
    { key: "install", label: "จัดส่ง + ติดตั้งโดยช่าง", sub: item.requires_install ? "สินค้านี้ต้องติดตั้ง · มีค่าติดตั้ง" : "เลือกได้ถ้าต้องการช่างประกอบ", ok: true },
  ];

  return (
    <main className="container sec product">
      <nav className="crumbs small muted">
        <Link to="/">หน้าแรก</Link> › {item.category_id && <><Link to={`/search?category=${item.category_id}`}>{item.category_name}</Link> › </>}<span>{item.name_th}</span>
      </nav>
      <div className="product-grid">
        <div className="product-gallery">
          <Placeholder src={item.image_url} alt={item.name_th} label={<>PRODUCT SHOT<br />1:1 · 1200 × 1200</>} />
          <div className="thumbs">
            {[1, 2, 3, 4].map((i) => (
              <Placeholder key={i} label={`${i}`} />
            ))}
          </div>
        </div>

        <div className="product-info">
          <div className="pcard-brand">{item.brand_name || "SB DESIGN"}</div>
          <h1>{item.name_th}</h1>
          <div className="muted">{item.variant}{item.spec ? ` · ${item.spec}` : ""}</div>
          <div className="mono small muted" style={{ marginTop: 4 }}>MATNR {item.matnr} · {item.sku}{item.barcode ? ` · ${item.barcode}` : ""}</div>

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

          <ul className="product-flags">
            <li><Icon name={item.is_takeaway_ok ? "shopping_bag" : "local_shipping"} size={18} /> {item.is_takeaway_ok ? "ยกกลับได้จากสาขา" : "จัดส่งจากคลังเท่านั้น"}</li>
            <li><Icon name="handyman" size={18} /> {item.requires_install ? "ต้องติดตั้งโดยช่าง (มีค่าติดตั้ง)" : "ไม่ต้องติดตั้ง / ประกอบเองได้"}</li>
            {item.weight_kg && <li><Icon name="scale" size={18} /> น้ำหนัก {num(item.weight_kg)} กก. · ปริมาตร {num(item.volume_m3)} ลบ.ม.</li>}
          </ul>

          {isStaff ? (
            <div className="note">โหมดพนักงาน: เพิ่มสินค้าให้ลูกค้าได้จากหน้า <Link to="/sales" className="strong">ตะกร้าที่กำลังดูแล</Link> (ค้นหา MATNR → ลงตะกร้า)</div>
          ) : (
            <div className="add-box">
              <div className="row between">
                <b>วิธีรับสินค้า</b>
                <div className="qty">
                  <button onClick={() => setQty(Math.max(1, qty - 1))} disabled={qty <= 1} aria-label="ลด"><Icon name="remove" size={18} /></button>
                  <span>{qty}</span>
                  <button onClick={() => setQty(qty + 1)} aria-label="เพิ่ม"><Icon name="add" size={18} /></button>
                </div>
              </div>
              <div className="opts">
                {modes.map((m) => (
                  <label key={m.key} className={"opt" + (mode === m.key ? " on" : "") + (m.ok ? "" : " off")}>
                    <input type="radio" name="mode" checked={mode === m.key} disabled={!m.ok} onChange={() => setMode(m.key)} />
                    <span className="grow">{m.label}<small>{m.sub}</small></span>
                  </label>
                ))}
              </div>
              <div className="product-actions">
                <button className="btn primary lg" onClick={addToCart} disabled={adding || !modes.find((m) => m.key === mode)?.ok}>
                  <Icon name="add_shopping_cart" size={20} /> {adding ? "กำลังเพิ่ม…" : "ลงตะกร้า"}
                </button>
                <button className="btn lg" onClick={checkStock} disabled={checking}>
                  <Icon name="inventory_2" size={20} /> {checking ? "กำลังเช็ค…" : "เช็คสต็อก"}
                </button>
              </div>
            </div>
          )}
          {isStaff && (
            <div className="product-actions">
              <button className="btn lg" onClick={checkStock} disabled={checking}>
                <Icon name="inventory_2" size={20} /> {checking ? "กำลังเช็ค…" : "เช็คสต็อกทุกสาขา"}
              </button>
            </div>
          )}
          <p className="small muted" style={{ marginTop: 6 }}>
            {plant ? `สาขาที่เลือก: ${plant.name}` : "ยังไม่ได้เลือกสาขา (เลือกได้ที่ “รับที่สาขา” ด้านบน)"}
          </p>

          {stock && (
            <div className={"stock-box" + (stock.stale ? " stale" : "")}>
              <div className="row between">
                <div className="strong"><Icon name={stock.stale ? "history" : "verified"} size={18} /> {stock.stale ? "ข้อมูลจาก cache (SAP ตอบช้า)" : "ข้อมูลสดจาก SAP"}</div>
                <div className="small muted">อัปเดต {thTime(stock.fetched_at)}{stock.stale ? ` · เก่า ${stock.stale_minutes} นาที` : ""}</div>
              </div>
              {isStaff ? (
                <ul className="stock-rows">
                  {stock.rows.map((r) => (
                    <li key={r.plant_code}>
                      <Icon name={r.plant_type === "warehouse" ? "warehouse" : "storefront"} size={20} />
                      <span className="grow">
                        <b>{r.plant_name}</b>
                        <small>{r.note || (r.atp_date ? `ATP: จัดส่งได้ ${thDate(r.atp_date)}` : "")}{r.reserved ? ` · จองแล้ว ${r.reserved}` : ""}</small>
                      </span>
                      <b className={r.available > 0 ? "green" : "red"}>{r.available} ชิ้น</b>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="stock-summary">
                  {stock.rows.map((r) => (
                    <div key={r.plant_code} className="row between">
                      <span><Icon name="storefront" size={18} /> {r.plant_name}</span>
                      <b className={r.available > 0 ? "green" : "red"}>{r.available > 0 ? `มีของ ${r.available} ชิ้น` : "ของหมดที่สาขานี้"}</b>
                    </div>
                  ))}
                  <div className="row between">
                    <span><Icon name="local_shipping" size={18} /> จัดส่งถึงบ้าน</span>
                    <b className={stock.available ? "green" : "red"}>{stock.available ? (stock.earliest_atp ? `ส่งได้เร็วสุด ${thDate(stock.earliest_atp)}` : "พร้อมส่ง") : "สั่งจอง / รอของเข้า"}</b>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {item.description && (
        <section className="product-desc">
          <h3>รายละเอียดสินค้า</h3>
          <p>{item.description}</p>
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
