import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import DeliveryPanel from "../components/DeliveryPanel";
import Icon from "../components/Icon";
import Placeholder from "../components/Placeholder";
import PromoPanel from "../components/PromoPanel";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { SUPPLY_LABEL } from "../lib/cart";
import { useContent } from "../lib/content";
import { baht, bahtWord, thDate, thTime } from "../lib/format";
import { useCartSocket } from "../lib/realtime";
import { useSales, type CustomerHit } from "../lib/sales";
import type { Availability, AvailabilityItem, CartItem, MaterialCard } from "../lib/types";

/** สีของป้ายสถานะ — แยกไว้ตรงนี้เพราะใช้ทั้งในตะกร้าและในหน้าค้นหา */
const AVAIL_TONE: Record<string, string> = { full: "green", split: "amber", short: "amber", none: "red", unknown: "red" };

function availText(a: AvailabilityItem): string {
  if (a.status === "unknown") return "SAP ไม่รู้จักรหัสนี้";
  if (a.status === "none") return "ไม่มีของ — SAP ยังไม่ให้วันส่ง";
  const parts: string[] = [];
  if (a.ready_qty) parts.push(`${a.ready_qty} ชิ้น${a.ready_date ? ` ส่งได้ ${thDate(a.ready_date)}` : ""}`);
  if (a.later_qty) parts.push(`อีก ${a.later_qty} ชิ้น${a.later_date ? ` รอถึง ${thDate(a.later_date)}` : ""}`);
  if (a.short_qty) parts.push(`ยังขาด ${a.short_qty} ชิ้น`);
  return parts.join(" · ");
}

function AvailBadge({ a }: { a: AvailabilityItem }) {
  return (
    <div className={"avail-badge " + AVAIL_TONE[a.status]}>
      <Icon name={a.status === "full" ? "check_circle" : a.status === "split" ? "schedule" : "error"} size={16} />
      <span><b>{a.label}</b> · {availText(a)}</span>
    </div>
  );
}

export default function SalesPage() {
  const auth = useAuth();
  const sales = useSales();
  const { plants } = useContent();
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [avail, setAvail] = useState<Availability | null>(null);
  const [live, setLive] = useState<string | null>(null);
  const [promoOpen, setPromoOpen] = useState(false);
  const [deliveryOpen, setDeliveryOpen] = useState(false);
  const [presoNo, setPresoNo] = useState<string | null>(null);
  const nav = useNavigate();

  // ผลเช็คของผูกกับตะกร้าใบนั้น — สลับแท็บหรือแก้ของแล้วต้องเช็คใหม่ ไม่งั้นเซลล์อ่านเลขของตะกร้าเก่า
  useEffect(() => setAvail(null), [sales.active?.id]);
  const cartStamp = (sales.active?.items || []).map((i) => `${i.matnr}x${i.qty}`).join("|");
  const availStale = avail !== null && avail.cart_id === sales.active?.id && avail.items.map((i) => `${i.matnr}x${i.qty}`).join("|") !== cartStamp;

  const checkStock = async () => {
    if (!sales.active) return;
    setBusy("stock");
    setMsg(null);
    try {
      setAvail(await apiPost<Availability>(`/sales/carts/${sales.active.id}/availability`, {}));
    } catch (e) {
      setAvail(null);
      setMsg(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  useEffect(() => {
    setPresoNo(null);
    if (!sales.active) return;
    apiGet<{ preso_no: string; status: string }[]>("/presos?status=draft&mine=true")
      .then((rows) => setPresoNo(rows.find((r) => (r as { cart_id?: string }).cart_id === sales.active?.id)?.preso_no || null))
      .catch(() => setPresoNo(null));
  }, [sales.active?.id]);

  const savePreso = async (): Promise<string | null> => {
    if (!sales.active) return null;
    setBusy("preso");
    setMsg(null);
    try {
      const p = await apiPost<{ preso_no: string }>("/presos", { cart_id: sales.active.id });
      setPresoNo(p.preso_no);
      setLive(`บันทึก Preso ${p.preso_no} แล้ว — ดึงกลับมาทำต่อได้ที่ "Preso ของฉัน"`);
      return p.preso_no;
    } catch (e) {
      setMsg(errorMessage(e));
      return null;
    } finally {
      setBusy(null);
    }
  };

  const makeQuotation = async (force = false) => {
    const no = presoNo || (await savePreso());
    if (!no) return;
    setBusy("quotation");
    setMsg(null);
    try {
      const q = await apiPost<{ quotation_no: string }>(`/presos/${no}/quotation`, { force });
      await sales.reload();
      nav(`/sales/quotations/${q.quotation_no}`);
    } catch (e) {
      const detail = (e as { detail?: { shortages?: { name: string; need: number; available: number }[]; message?: string } }).detail;
      if (detail && typeof detail === "object" && detail.shortages) {
        const lines = detail.shortages.map((s) => `• ${s.name}: ต้องการ ${s.need} มี ${s.available}`).join("\n");
        if (confirm(`${detail.message}\n\n${lines}\n\nออกใบเสนอราคาทั้งที่ของไม่พอ?`)) return makeQuotation(true);
      } else setMsg(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  // realtime: ลูกค้ากดเก็บไว้/ลบออก/แก้จำนวนจากมือถือ → เซลล์เห็นทันที
  useCartSocket(sales.active?.id, (evt) => {
    if (evt.type === "hello") return;
    sales.reloadActive();
    if (evt.type === "item_acked") setLive("ลูกค้ากด “เก็บไว้” สินค้าที่คุณเพิ่ม");
    else if (evt.type === "item_removed" && evt.added_by !== "sales") setLive("ลูกค้าลบสินค้าออกจากตะกร้า");
    else if (evt.type === "item_added" && evt.added_by === "customer") setLive("ลูกค้าเพิ่มสินค้าเองจากมือถือ");
  });
  useEffect(() => {
    if (!live) return;
    const t = setTimeout(() => setLive(null), 5000);
    return () => clearTimeout(t);
  }, [live]);

  if (!sales.enabled) {
    return (
      <main className="container sec">
        <div className="card" style={{ maxWidth: 560 }}>
          <b>โหมดพนักงานขาย</b>
          <p className="muted small">ต้องเข้าสู่ระบบด้วยบัญชีพนักงานขาย (เช่น SA-104) เพื่อใช้หน้านี้</p>
          <button className="btn dark" onClick={auth.openLogin}>เข้าสู่ระบบพนักงาน</button>
        </div>
      </main>
    );
  }

  const cart = sales.active;
  const plantName = (code: string | null) => plants.find((p) => p.plant_code === code)?.name || code || "";
  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    setMsg(null);
    try {
      await fn();
    } catch (e) {
      setMsg(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <main className="container sec sales">
      <Link to="/search" className="row small muted" style={{ marginBottom: 10 }}><Icon name="arrow_back" size={18} /> กลับไปช้อปต่อ</Link>
      <h1 className="cart-title">ตะกร้าที่กำลังดูแล</h1>

      {/* session bar */}
      <div className="sess-bar">
        <div className="row between wrap">
          <div className="row"><Icon name="support_agent" size={22} /> <b>โหมดพนักงานขาย · {auth.user?.name}</b> {cart && <span className="chip light">SESSION {cart.no}</span>}</div>
          <div className="row">
            <Link to="/sales/presos" className="btn sm" style={{ background: "#fff" }}><Icon name="folder_open" size={18} /> Preso ของฉัน</Link>
            <button className="btn sm" style={{ background: "#fff" }} onClick={() => run("open", () => sales.openCart())} disabled={busy === "open"}><Icon name="add" size={18} /> เปิดตะกร้าใหม่</button>
          </div>
        </div>
        <div className="sess-tabs">
          {sales.sessions.map((s) => (
            <div key={s.id} className={"sess-tab" + (s.id === sales.activeId ? " on" : "")} onClick={() => sales.setActiveId(s.id)} role="button" tabIndex={0}>
              <Icon name="shopping_basket" size={18} />
              <span className="grow">
                <b>{s.customer_name || `ตะกร้าใหม่ ${s.no}`}</b>
                <small>{s.count > 0 ? `${s.count} ชิ้น · ${bahtWord(s.subtotal)}` : "ยังไม่มีสินค้า"}{s.customer_tier ? ` · ${s.customer_tier}` : ""}</small>
              </span>
              <button className="sess-close" aria-label="ปิดตะกร้า" onClick={(e) => { e.stopPropagation(); if (confirm(`ปิดตะกร้า ${s.customer_name || s.no}? สิทธิ์ของคุณจะหมดทันที`)) run("close", () => sales.closeCart(s.id)); }}><Icon name="close" size={16} /></button>
            </div>
          ))}
          {sales.sessions.length === 0 && !sales.loading && <span className="small" style={{ opacity: .8 }}>ยังไม่มีตะกร้า — กด "เปิดตะกร้าใหม่"</span>}
        </div>
        {cart && (
          <div className="sess-cust">
            <span className="small" style={{ opacity: .8 }}>ตะกร้าของลูกค้า:</span>
            {cart.customer ? (
              <>
                <span className="cust-pill"><Icon name="how_to_reg" size={18} /> <b>{cart.customer.name}</b> · CUST {cart.customer.sap_customer_no || "-"} · {cart.customer.tier || "ทั่วไป"}</span>
                <button className="link-btn small" style={{ color: "#fff" }} onClick={() => run("detach", () => sales.detach())} disabled={busy === "detach"}>ตัดการเชื่อมต่อ</button>
              </>
            ) : (
              <>
                <CustomerSearch onPick={(hit) => run("attach", () => sales.attach(hit.sap_customer_no || hit.email || hit.phone || ""))} search={sales.searchCustomers} />
                <span className="small" style={{ opacity: .8 }}>ลูกค้าใหม่ยังไม่มีในระบบก็ทำต่อได้ — ใส่สินค้าไปก่อน ค่อยผูกลูกค้าตอนจะออกใบเสนอราคา</span>
              </>
            )}
            <button className="btn primary sm" style={{ marginLeft: "auto" }} onClick={() => setSearchOpen(true)}><Icon name="add_shopping_cart" size={18} /> เพิ่มสินค้าให้ลูกค้า</button>
          </div>
        )}
      </div>

      {msg && <div className="note err" style={{ margin: "12px 0" }}>{msg}</div>}

      {cart ? (
        <div className="cart-grid">
          <div className="cart-main">
            {cart.items.length === 0 ? (
              <div className="cart-empty">
                <Icon name="search" size={44} />
                <div className="strong">ยังไม่มีสินค้าในตะกร้านี้</div>
                <button className="btn dark" onClick={() => setSearchOpen(true)}>ค้นหาสินค้า (MATNR) เพื่อเพิ่มให้ลูกค้า</button>
              </div>
            ) : (
              <>
                <p className="cart-intro">สินค้า {cart.count} ชิ้น · ยอดชั่วคราว {bahtWord(cart.subtotal)}{cart.customer ? ` · ราคาสมาชิก ${cart.customer.tier || "ทั่วไป"}` : " · ยังไม่ผูกลูกค้า (ราคาปกติ)"}</p>
                {deliveryOpen && (
                  <div style={{ marginBottom: 14 }}>
                    <DeliveryPanel key={cart.id} cart={cart} defaultPostcode={cart.customer?.default_postcode} defaultAddress={cart.customer?.default_address} onChanged={sales.reloadActive} />
                  </div>
                )}
                <div className="cart-items">
                  {cart.items.map((it) => (
                    <SalesRow key={it.id} it={it} busy={busy === it.id} plantName={plantName(it.plant_code)}
                      avail={avail?.items.find((a) => a.item_id === it.id) || null} availStale={availStale}
                      onInc={() => run(it.id, () => sales.updateItem(it.id, { qty: it.qty + 1 }))}
                      onDec={() => it.qty > 1 && run(it.id, () => sales.updateItem(it.id, { qty: it.qty - 1 }))}
                      onRemove={() => run(it.id, () => sales.removeItem(it.id))}
                      onNote={(note) => run(it.id, () => sales.updateItem(it.id, { note }))} />
                  ))}
                </div>
              </>
            )}
          </div>
          <aside className="cart-side">
            <div className="summary">
              <h3>สรุปคำสั่งซื้อ</h3>
              <div className="sum-row"><span>สินค้า ({cart.count})</span><b>{bahtWord(cart.subtotal)}</b></div>
              {cart.totals && Number(cart.totals.member_savings) > 0 && <div className="sum-row"><span>ราคาสมาชิก (รวมแล้ว)</span><span className="green">−{bahtWord(cart.totals.member_savings)}</span></div>}
              {cart.totals && cart.totals.lines.length === 0 && (
                <div className="sum-row"><span>ส่วนลด</span><button className="link-btn small" onClick={() => setPromoOpen(true)}>รอเช็คโปร</button></div>
              )}
              {cart.totals?.lines.map((l) => (
                <div key={l.id} className="sum-row"><span>{l.title}{l.status === "pending_approval" ? " (รออนุมัติ)" : ""}</span><span className={l.status === "applied" ? "green" : "muted"}>−{bahtWord(l.amount)}</span></div>
              ))}
              {cart.totals?.warnings.map((w) => (
                <div key={w} className="note warn small">{w}</div>
              ))}
              <div className="sum-row"><span>ค่าขนส่ง{cart.totals && Number(cart.totals.install_fee) > 0 ? " + ติดตั้ง" : ""}</span>
                {cart.delivery?.quoted_at && cart.totals ? <b>{bahtWord(Number(cart.totals.shipping_fee) + Number(cart.totals.install_fee) - Number(cart.totals.shipping_discount))}</b> : <button className="link-btn small" onClick={() => setDeliveryOpen(true)}>รอคำนวณ</button>}
              </div>
              {cart.delivery?.slot_date && <div className="sum-row small muted"><span>คิวจัดส่ง</span><span>{thDate(cart.delivery.slot_date)} {cart.delivery.slot_period === "am" ? "เช้า" : "บ่าย"} · เขต {cart.delivery.zone}</span></div>}
              <div className="sum-total"><span>ยอดรวมทั้งบิล (รวม VAT)</span><b>{bahtWord(cart.totals?.grand_total ?? cart.subtotal)}</b></div>
              <div className="col" style={{ marginTop: 12 }}>
                {/* เช็คทั้งตะกร้าในการยิงครั้งเดียว — SAP จำลองทั้งบิล บรรทัดแรกกินของก่อน ยิงทีละชิ้นจะเห็นของตัวเดียวกันซ้ำแล้วขายเกิน */}
                <button className="btn block" onClick={checkStock} disabled={busy === "stock" || cart.items.length === 0}>
                  <Icon name="inventory_2" size={18} /> {busy === "stock" ? "กำลังถาม SAP…" : avail ? "เช็คของกับ SAP อีกครั้ง" : "เช็คของกับ SAP"}
                </button>
                {avail && avail.cart_id === cart.id && (
                  <div className={"note small " + (availStale ? "warn" : avail.all_ok ? "ok" : "warn")}>
                    {availStale ? "ของในตะกร้าเปลี่ยนหลังเช็คครั้งล่าสุด — กดเช็คใหม่ก่อนยืนยันกับลูกค้า" : avail.message}
                    <div className="tiny muted" style={{ marginTop: 4 }}>
                      ถามวันส่ง {thDate(avail.req_date)} · ลูกค้า {avail.customer_no}{avail.is_walkin ? " (walk-in)" : ""} · เช็คเมื่อ {thTime(avail.checked_at)}
                    </div>
                  </div>
                )}
                <button className="btn block" onClick={() => setPromoOpen(true)} disabled={cart.items.length === 0}><Icon name="sell" size={18} /> {cart.totals && cart.totals.lines.length > 0 ? "แก้ไขโปรโมชั่น / ส่วนลด" : "เช็คโปรโมชั่น"}</button>
                <button className="btn block" onClick={() => setDeliveryOpen((v) => !v)} disabled={cart.items.length === 0}><Icon name="local_shipping" size={18} /> {cart.delivery?.quoted_at ? "แก้ไขค่าส่ง / คิวจัดส่ง" : "คิดค่าส่ง + คิวจัดส่ง"}</button>
                <button className="btn block" disabled={busy === "preso" || cart.items.length === 0} onClick={() => savePreso()}><Icon name="save" size={18} /> {presoNo ? `บันทึกแล้ว · ${presoNo}` : "Save Preso"}</button>
                <button className="btn primary block" disabled={!cart.customer || busy !== null || cart.items.length === 0} title={cart.customer ? "" : "ต้องผูกลูกค้าก่อน"} onClick={() => makeQuotation()}>สร้างใบเสนอราคา</button>
              </div>
              <p className="tiny muted" style={{ marginTop: 10 }}>{cart.customer ? "ใบเสนอราคาจะยืนราคา 7 วัน แล้วส่งต่อให้ระบบหลังบ้าน convert เป็น SO ใน SAP" : "ต้องค้นหาและผูกลูกค้าก่อนจึงจะออกใบเสนอราคาได้"}</p>
              {cart.expires_at && <p className="tiny muted">ตะกร้านี้หมดอายุอัตโนมัติ {thDate(cart.expires_at)} {thTime(cart.expires_at)} (ต่ออายุทุกครั้งที่ใช้งาน)</p>}
            </div>
          </aside>
        </div>
      ) : (
        /* ลูกค้าใหม่ที่ยังไม่มีบัญชี/ยังไม่มีตะกร้า — เซลล์เปิดตะกร้าของตัวเองแล้วเริ่มจัดของได้เลย ค่อยผูกลูกค้าทีหลัง */
        !sales.loading && (
          <div className="cart-empty">
            <Icon name="shopping_basket" size={44} />
            <div className="strong">{sales.sessions.length ? "เลือกตะกร้าด้านบนเพื่อทำงานต่อ" : "ยังไม่มีตะกร้าที่กำลังดูแล"}</div>
            <p className="small muted" style={{ maxWidth: 460, textAlign: "center", margin: 0 }}>
              ลูกค้าใหม่ที่ยังไม่มีบัญชีก็เริ่มได้ — เปิดตะกร้าของคุณเองแล้วใส่สินค้าได้ทันที (คิดราคาปกติไปก่อน) ค่อยค้นหาและผูกลูกค้าทีหลังเพื่อใช้ราคาสมาชิกและออกใบเสนอราคา
            </p>
            <button className="btn dark" onClick={() => run("open", () => sales.openCart())} disabled={busy === "open"}>
              <Icon name="add" size={18} /> เปิดตะกร้าใหม่
            </button>
          </div>
        )
      )}

      {searchOpen && <MaterialSearchModal onClose={() => setSearchOpen(false)} target={cart?.customer?.name || `ตะกร้า ${cart?.no || ""}`} search={sales.searchMaterials}
        onAdd={(m, mode, plant) => run("add", async () => { await sales.addItem(m.matnr, 1, mode, plant); setSearchOpen(false); })} />}
      {promoOpen && cart && <PromoPanel cart={cart} isStaff onClose={() => setPromoOpen(false)} onCartChange={(c) => sales.setActive(c)} />}
      {live && <div className="toast" role="status"><Icon name="notifications_active" size={20} /> {live}</div>}
    </main>
  );
}

function SalesRow({ it, busy, plantName, avail, availStale, onInc, onDec, onRemove, onNote }: { it: CartItem; busy: boolean; plantName: string; avail: AvailabilityItem | null; availStale: boolean; onInc: () => void; onDec: () => void; onRemove: () => void; onNote: (n: string) => void }) {
  const [note, setNote] = useState(it.note || "");
  return (
    <div className="cart-row sales-row">
      <Link to={`/p/${it.matnr}`} className="cart-img"><Placeholder src={it.image_url} label="1:1" /></Link>
      <div className="cart-info">
        <div className="row wrap" style={{ gap: 6, marginBottom: 4 }}>
          <span className={"chip " + (it.added_by === "sales" ? "green" : "light")}>{it.added_by === "sales" ? "เซลล์เพิ่ม" : "จากตะกร้าลูกค้า"}</span>
          {it.pending_ack && <span className="chip amber">รอลูกค้ายืนยัน</span>}
          <span className="pill"><Icon name={it.supply_mode === "takeaway" ? "shopping_bag" : it.supply_mode === "install" ? "handyman" : "local_shipping"} size={14} /> {SUPPLY_LABEL[it.supply_mode]}{it.plant_code ? ` · ${plantName}` : ""}{it.atp_date ? ` · ATP ${thDate(it.atp_date)}` : ""}</span>
        </div>
        <Link to={`/p/${it.matnr}`} className="cart-name">{it.name}</Link>
        <div className="small muted">{it.variant}{it.spec ? ` · ${it.spec}` : ""}</div>
        {/* ส่วนใหญ่ SKU = MATNR ตัวเดียวกัน โชว์ซ้ำสองรอบไม่มีประโยชน์ */}
        <div className="mono tiny muted">MATNR {it.matnr}{it.sku && it.sku !== it.matnr ? ` · ${it.sku}` : ""}</div>
        <div className="small muted" style={{ marginTop: 4 }}>{bahtWord(it.unit_price)} / ชิ้น · {it.price_tier}</div>
        {/* ผลเช็คของมาจากการยิงทั้งตะกร้าครั้งเดียว (ปุ่มในสรุปคำสั่งซื้อ) — บรรทัดนี้แค่แสดงผลของตัวเอง */}
        {avail && <div className={availStale ? "avail-stale" : undefined}><AvailBadge a={avail} /></div>}
        <form className="row" style={{ marginTop: 8 }} onSubmit={(e) => { e.preventDefault(); onNote(note); }}>
          <input className="hdr-pop-input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="หมายเหตุ เช่น รอลูกค้าวัดห้อง" />
          <button className="btn sm" type="submit" disabled={busy || note === (it.note || "")}>บันทึก</button>
        </form>
      </div>
      {/* ริมขวา: ถังขยะอยู่บนสุด · ยอดของบรรทัดนี้ · ปุ่มจำนวนอยู่ฝั่งเดียวกับราคา */}
      <div className="sales-side">
        <button className="icon-btn danger" onClick={onRemove} disabled={busy} title="ลบออกจากตะกร้า" aria-label="ลบออกจากตะกร้า"><Icon name="delete" size={18} /></button>
        <b className="cart-line">{bahtWord(it.line_total)}</b>
        <div className="qty sm">
          <button onClick={onDec} disabled={busy || it.qty <= 1} aria-label="ลด"><Icon name="remove" size={16} /></button>
          <span>{it.qty}</span>
          <button onClick={onInc} disabled={busy} aria-label="เพิ่ม"><Icon name="add" size={16} /></button>
        </div>
      </div>
    </div>
  );
}

function CustomerSearch({ onPick, search }: { onPick: (hit: CustomerHit) => void; search: (q: string) => Promise<CustomerHit[]> }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<CustomerHit[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      setHits(await search(q));
    } catch (e2) {
      setErr(errorMessage(e2));
    }
  };
  return (
    <div className="cust-search">
      <form className="row" onSubmit={submit}>
        <Icon name="person_search" size={20} />
        <input className="hdr-pop-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="ค้นหาลูกค้า (เลขสมาชิก / เบอร์ / อีเมล)" />
        <button className="btn sm" style={{ background: "#fff" }} type="submit" disabled={q.trim().length < 2}>ค้นหา</button>
        <button className="btn sm" style={{ background: "#fff" }} type="button" onClick={() => setQ("089-234-4471")} title="สแกน QR (จำลอง)"><Icon name="qr_code_scanner" size={18} /></button>
      </form>
      {err && <div className="note err small" style={{ marginTop: 6 }}>{err}</div>}
      {hits && (
        <div className="cust-hits">
          {hits.length === 0 && <div className="small">ไม่พบลูกค้า — ลูกค้าใหม่ walk-in ให้ลงทะเบียนด้วย OTP ก่อน</div>}
          {hits.map((h) => (
            <div key={(h.sap_customer_no || "") + (h.email || "")} className="cust-hit">
              <span className="avatar">{h.name.slice(0, 2)}</span>
              <span className="grow">
                <b>{h.name}</b> · {h.tier || "ทั่วไป"}
                <small>CUST {h.sap_customer_no || "-"} · {h.phone || "-"} · {h.email || "-"}{h.source === "sap" ? " · จาก SAP" : ""}</small>
                {h.online_cart_count > 0 && <small className="green strong">มีตะกร้าออนไลน์ {h.online_cart_count} ชิ้น → จะรวมเข้าตะกร้านี้</small>}
              </span>
              <button className="btn dark sm" onClick={() => onPick(h)}>ผูกลูกค้า</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MaterialSearchModal({ onClose, target, search, onAdd }: { onClose: () => void; target: string; search: (q: string) => Promise<SearchOutLike>; onAdd: (m: MaterialCard, mode: string | null, plant: string | null) => void }) {
  const { plants } = useContent();
  const [q, setQ] = useState("");
  const [items, setItems] = useState<MaterialCard[]>([]);
  const [loading, setLoading] = useState(false);
  // เช็คของรายตัวก่อนลงตะกร้า — ตัวเลขนี้ยังไม่หักของที่อยู่ในตะกร้าแล้ว ต้องกดเช็คทั้งบิลอีกทีหลังลงตะกร้า
  const [one, setOne] = useState<Record<string, AvailabilityItem | "loading" | string>>({});
  const checkOne = async (m: MaterialCard) => {
    setOne((s) => ({ ...s, [m.matnr]: "loading" }));
    try {
      const r = await apiPost<AvailabilityItem>("/sales/availability", { matnr: m.matnr, qty: 1 });
      setOne((s) => ({ ...s, [m.matnr]: r }));
    } catch (e) {
      setOne((s) => ({ ...s, [m.matnr]: errorMessage(e) }));
    }
  };
  useEffect(() => {
    let alive = true;
    setLoading(true);
    const t = setTimeout(() => {
      search(q).then((r) => alive && setItems(r.items)).finally(() => alive && setLoading(false));
    }, 200);
    return () => { alive = false; clearTimeout(t); };
  }, [q, search]);
  const store = plants.find((p) => p.type === "store");
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>ค้นหาสินค้า (MATNR) เพื่อเพิ่มให้ <span className="green">{target}</span></h2>
          <button className="icon-btn" onClick={onClose} aria-label="ปิด"><Icon name="close" /></button>
        </div>
        <div className="row" style={{ marginBottom: 12 }}>
          <Icon name="search" size={20} />
          <input className="hdr-pop-input" autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="ชื่อสินค้า / รหัสแมท / บาร์โค้ด" />
          <button className="btn sm" type="button" onClick={() => setQ("10023841")}><Icon name="barcode_scanner" size={18} /> สแกน</button>
        </div>
        {loading && items.length === 0 && <div className="ph" style={{ height: 120 }}>กำลังค้นหา…</div>}
        {!loading && items.length === 0 && <div className="muted small">ไม่พบสินค้า</div>}
        <div className="mat-results">
          {items.map((m) => {
            const res = one[m.matnr];
            return (
              <div key={m.matnr} className="mat-hit">
                <Placeholder src={m.image_url} label="1:1" className="mat-img" />
                <div className="grow">
                  <b>{m.name_th}</b>
                  <div className="small muted">{m.variant}{m.spec ? ` · ${m.spec}` : ""}</div>
                  <div className="mono tiny muted">MATNR {m.matnr}{m.sku && m.sku !== m.matnr ? ` · ${m.sku}` : ""}</div>
                  <div className="row wrap" style={{ gap: 8, marginTop: 4 }}>
                    <b>{baht(m.standard_price)}</b>
                    {m.member_price && <span className="small green">สมาชิก {baht(m.member_price)}</span>}
                  </div>
                  {res === "loading" && <div className="tiny muted" style={{ marginTop: 4 }}>กำลังถาม SAP…</div>}
                  {typeof res === "string" && res !== "loading" && <div className="note err small" style={{ marginTop: 4 }}>{res}</div>}
                  {res && typeof res !== "string" && <AvailBadge a={res} />}
                </div>
                <div className="col">
                  <button className="btn sm" onClick={() => checkOne(m)} disabled={res === "loading"}><Icon name="inventory_2" size={16} /> เช็คของกับ SAP</button>
                  <button className="btn dark sm" onClick={() => onAdd(m, m.requires_install ? "install" : store && m.is_takeaway_ok ? "takeaway" : "ship", store && m.is_takeaway_ok && !m.requires_install ? store.plant_code : null)}>ลงตะกร้า</button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

type SearchOutLike = { items: MaterialCard[] };
