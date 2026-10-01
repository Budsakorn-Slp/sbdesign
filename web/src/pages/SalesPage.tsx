import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import DeliveryPanel from "../components/DeliveryPanel";
import StaffShippingCharge from "../components/StaffShippingCharge";
import Icon from "../components/Icon";
import Placeholder from "../components/Placeholder";
import { imageSources } from "../lib/images";
import PromoPanel from "../components/PromoPanel";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { SUPPLY_LABEL, shipNeedsReview } from "../lib/cart";
import { useContent } from "../lib/content";
import { baht, bahtWord, thDate, thTime } from "../lib/format";
import { useCartSocket } from "../lib/realtime";
import { useSales, type CustomerHit } from "../lib/sales";
import type { Availability, AvailabilityItem, CartItem, MaterialCard } from "../lib/types";

/** สีของป้ายสถานะ — แยกไว้ตรงนี้เพราะใช้ทั้งในตะกร้าและในหน้าค้นหา */
const AVAIL_TONE: Record<string, string> = { full: "green", split: "amber", short: "amber", none: "red", unknown: "red" };

function availText(a: AvailabilityItem): string {
  // สองเคสนี้คำอธิบายเท่ากับป้ายสถานะอยู่แล้ว ส่งค่าว่างกลับไปกันข้อความซ้ำสองรอบ
  // ("SAP ไม่รู้จักรหัสนี้ · SAP ไม่รู้จักรหัสนี้")
  if (a.status === "unknown") return "";
  if (a.status === "none") return "SAP ยังไม่ให้วันส่ง";
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
      <span><b>{a.label}</b>{availText(a) ? ` · ${availText(a)}` : ""}</span>
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
  const [sessOpen, setSessOpen] = useState(false); // แผงตะกร้า/ลูกค้าบนจอเล็ก (จอใหญ่กางเสมอ)
  const [sheet, setSheet] = useState(false); // แผงสรุปบนจอเล็กกางอยู่ไหม (จอใหญ่ไม่ใช้ค่านี้)
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

  type WithPreso = { items?: unknown[]; preso?: { steps: { key: string; ok: boolean }[] } | null } | null;

  /** กดปุ่ม Save PRE SO ได้ไหม — ด่านอื่นต้องครบ ส่วน "ของไม่พอ" ปล่อยให้กดได้
   *  แล้วไปถามยืนยันตอนกด (ลูกค้ายอมรอของ) ถ้าปิดปุ่มไปเลยจะไม่มีทางยืนยัน */
  // Preso เป็นร่าง — บันทึกค้างไว้ได้ตลอด ขอแค่มีของในตะกร้า
  // (ลูกค้าเดินไปดูของต่อกลางคัน พนักงานต้องเก็บงานที่ทำมาไว้ได้ ไม่ใช่เสียทั้งใบ)
  const canSavePreso = (c: WithPreso) => Boolean(c?.items?.length);
  // ส่วนใบเสนอราคาต้องครบทุกด่าน เพราะเอกสารออกไปถึงมือลูกค้าและส่งเข้า SAP จริง
  const allStepsDone = (c: WithPreso) => Boolean(c?.preso?.steps.every((st) => st.ok || st.key === "stock"));

  /** บันทึกใบ PRE แล้ว และใบยังตรงกับตะกร้าปัจจุบัน → ถึงคิวออกใบเสนอราคา */
  const readyForQuotation = (c: WithPreso) => Boolean(presoNo && allStepsDone(c));

  const savePreso = async (force = false): Promise<string | null> => {
    if (!sales.active) return null;
    setBusy("preso");
    setMsg(null);
    try {
      const p = await apiPost<{ preso_no: string }>("/presos", { cart_id: sales.active.id, force });
      setPresoNo(p.preso_no);
      setLive(`บันทึก Preso ${p.preso_no} แล้ว — ดึงกลับมาทำต่อได้ที่ "Preso ของฉัน"`);
      return p.preso_no;
    } catch (e) {
      // ติดด่านเดียวที่ข้ามได้คือ "ของไม่พอ" — ถ้าลูกค้ายอมรอของ เซลล์ยืนยันแล้วบันทึกต่อได้
      // (ระบบบันทึกไว้ว่าใครเป็นคนข้าม) ด่านอื่นข้ามไม่ได้ บอกให้ไปทำให้ครบก่อน
      const stuck = sales.active?.preso?.steps.find((st) => !st.ok);
      if (!force && stuck?.key === "stock" && confirm(`${errorMessage(e)}

บันทึกใบ PRE ทั้งที่ของไม่พอ? (ลูกค้ายอมรอของ)`)) {
        return savePreso(true);
      }
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
          <Link className="btn dark" to="/staff">เข้าสู่ระบบพนักงาน</Link>
        </div>
      </main>
    );
  }

  const cart = sales.active;
  // บรรทัดค่าขนส่งในตะกร้า (role tier = ตามยอดบิล · extra = ค่าส่งเพิ่มเติมจากปลายทาง)
  // ยอดพวกนี้ไม่ถูกนับเป็น "สินค้า" อยู่แล้ว ฝั่งหลังบ้านโยนไปรวมที่ค่าขนส่งให้
  // ธง is_charge มาจากไฟล์กฎ — เติมรหัสใหม่ในไฟล์แล้วหน้านี้รู้เอง ไม่ต้องตามแก้ลิสต์
  const shipLines = (cart?.items || []).filter((it) => it.is_charge && it.selected);
  // บรรทัดค่าขนส่งโชว์ในลิสต์ด้วย — พนักงานต้องเห็นว่า Mat ตัวไหนถูกเปิดเข้าบิลไปแล้ว
  // (เลข MATNR คือสิ่งที่ใช้คุยกับคลัง/SAP) แต่ไม่นับรวมใน "สินค้า (N)"
  // เพราะมันเป็นค่าบริการ ไม่ใช่ของที่ลูกค้าเลือก — ยอดก็ไปอยู่บรรทัดค่าขนส่งของกล่องสรุป
  const goods = (cart?.items || []).filter((it) => !it.is_charge);
  const rows = cart?.items || [];

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

      {/* แถบโหมดพนักงานขาย — จอเล็กพับส่วนตะกร้า/ลูกค้าไว้ใต้หัวแถบ กดที่หัวแถบเพื่อกาง
          (เดิมกางทั้งหมดตลอด กินพื้นที่ครึ่งจอก่อนจะเห็นสินค้าสักชิ้น) · จอใหญ่กางอยู่เสมอ */}
      <div className={"sess-bar" + (sessOpen ? " open" : "")}>
        <button className="sess-head" onClick={() => setSessOpen((v) => !v)} aria-expanded={sessOpen} aria-controls="sess-panel">
          <span className="sess-avatar"><Icon name="support_agent" size={20} /></span>
          <span className="sess-who"><small>โหมดพนักงานขาย</small><b>{auth.user?.name}</b></span>
          {cart && <span className="chip light sess-chip">SESSION<i>{cart.no}</i></span>}
          <Icon name="chevron_right" size={20} className="sess-caret" />
        </button>
        <div className="sess-acts">
          <Link to="/sales/presos" className="btn sm sess-act"><Icon name="folder_open" size={18} /> Preso ของฉัน</Link>
          <button className="btn sm sess-act" onClick={() => run("open", () => sales.openCart())} disabled={busy === "open"}><Icon name="add" size={18} /> เปิดตะกร้าใหม่</button>
          {/* จอเล็ก: ปุ่มเพิ่มสินค้าต้องอยู่นอกแผงที่พับเก็บ — งานหลักของหน้านี้คือหยิบของใส่ตะกร้า
              ถ้าซ่อนไว้หลังลูกศรกางแผง เซลล์ที่ยืนอยู่กับลูกค้าจะหาไม่เจอ
              (จอใหญ่ CSS ซ่อนปุ่มนี้ เพราะแถวลูกค้ากางอยู่แล้วและมีปุ่มเดิมอยู่ในนั้น) */}
          {cart && (
            <button className="btn sm sess-act sess-add-m" onClick={() => setSearchOpen(true)} aria-label="เพิ่มสินค้าให้ลูกค้า" title="เพิ่มสินค้าให้ลูกค้า">
              <Icon name="add_shopping_cart" size={18} />
            </button>
          )}
        </div>

        <div className="sess-panel" id="sess-panel">
        <div className="sess-tabs">
          {sales.sessions.map((s) => (
            <div key={s.id} className={"sess-tab" + (s.id === sales.activeId ? " on" : "")} onClick={() => sales.setActiveId(s.id)} role="button" tabIndex={0}>
              <Icon name="shopping_basket" size={18} />
              <span className="grow">
                <b>{s.customer_name || `ตะกร้าใหม่ ${s.no}`}</b>
                <small>{s.count > 0 ? `${s.count} ชิ้น · ${bahtWord(s.subtotal)}` : "ยังไม่มีสินค้า"}</small>
              </span>
              <button className="sess-close" aria-label="ปิดตะกร้า" onClick={(e) => { e.stopPropagation(); if (confirm(`ปิดตะกร้า ${s.customer_name || s.no}? สิทธิ์ของคุณจะหมดทันที`)) run("close", () => sales.closeCart(s.id)); }}><Icon name="close" size={16} /></button>
            </div>
          ))}
          {sales.sessions.length === 0 && !sales.loading && <span className="small sess-lbl">ยังไม่มีตะกร้า — กด "เปิดตะกร้าใหม่"</span>}
        </div>
        {cart && (
          <div className="sess-cust" id="sales-customer">
            <span className="small sess-lbl">ตะกร้าของลูกค้า:</span>
            {cart.customer ? (
              <>
                <span className="cust-pill"><Icon name="how_to_reg" size={18} /> <b>{cart.customer.name}</b> · CUST {cart.customer.sap_customer_no || "-"} · {(cart.customer.points || 0).toLocaleString()} พ้อยท์</span>
                <button className="link-btn small sess-detach" onClick={() => run("detach", () => sales.detach())} disabled={busy === "detach"}>ตัดการเชื่อมต่อ</button>
              </>
            ) : (
              <>
                <CustomerSearch onPick={(hit) => run("attach", () => sales.attach(hit.sap_customer_no || hit.email || hit.phone || ""))} search={sales.searchCustomers} />
                <span className="sess-newcust">
                  <span className="sess-ic"><Icon name="person_add" size={22} /></span>
                  <span><b>ลูกค้าใหม่ยังไม่มีในระบบ</b><small>ใส่สินค้าไปก่อนได้ ค่อยผูกลูกค้าตอนจะออกใบเสนอราคา</small></span>
                </span>
              </>
            )}
            <button className="btn primary sess-add" onClick={() => setSearchOpen(true)}><Icon name="add_shopping_cart" size={18} /> เพิ่มสินค้าให้ลูกค้า</button>
          </div>
        )}
        </div>
      </div>

      {msg && <div className="note err" style={{ margin: "12px 0" }}>{msg}</div>}

      {cart ? (
        <div className="cart-grid has-sheet">
          <div className="cart-main">
            {cart.items.length === 0 ? (
              <div className="cart-empty">
                <Icon name="search" size={44} />
                <div className="strong">ยังไม่มีสินค้าในตะกร้านี้</div>
                <button className="btn dark" onClick={() => setSearchOpen(true)}>ค้นหาสินค้า (MATNR) เพื่อเพิ่มให้ลูกค้า</button>
              </div>
            ) : (
              <>
                <p className="cart-intro">สินค้า {cart.count} ชิ้น · ยอดชั่วคราว {bahtWord(cart.subtotal)}{cart.customer ? "" : " · ยังไม่ผูกลูกค้า"}</p>
                {/* ค่าขนส่งแบบ "เปิด Mat" ของฝั่งขาย — อยู่นอกบล็อกคิวจัดส่ง เพราะใช้ได้แม้ยังไม่กรอกที่อยู่
                    (เทียร์คิดจากยอดบิลอย่างเดียว ไม่ได้ผูกกับปลายทาง) */}
                <StaffShippingCharge key={cart.id} cartId={cart.id} rev={cart.updated_at} onChanged={sales.reloadActive} />
                {/* แถบติ๊กเลือก — ยอดบิลคิดจากรายการที่ติ๊กเท่านั้น ถ้าไม่มีช่องนี้ ของที่ลูกค้า
                    เคยไม่ติ๊กไว้บนเว็บจะหายจากยอดโดยพนักงานมองไม่เห็นและกดแก้ไม่ได้ */}
                <div className="cart-bulk">
                  <label className="row">
                    <input
                      type="checkbox"
                      className="cart-pick"
                      checked={goods.length > 0 && goods.every((it) => it.selected)}
                      onChange={(e) => run("all", () => sales.selectItems(null, e.target.checked))}
                    />
                    เลือกทั้งหมด
                  </label>
                  <span className="small muted">คิดเงิน {goods.filter((it) => it.selected).length} จาก {goods.length} รายการ</span>
                </div>
                <div className="cart-items">
                  {rows.map((it) => (
                    <SalesRow key={it.id} it={it} busy={busy === it.id} plantName={plantName(it.plant_code)}
                      onPick={() => run(it.id, () => sales.selectItems([it.id], !it.selected))}
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
          {/* จอเล็ก: สรุปคำสั่งซื้อกลายเป็นแผงลอยจากขอบล่าง — เดิมต้องเลื่อนผ่านสินค้าทั้งตะกร้า
              ลงไปสุดหน้าถึงจะกดเช็คสต็อก/เช็คโปร/ออกใบเสนอราคาได้ ซึ่งเป็นงานที่เซลล์กดบ่อยสุด
              ยอดรวมกับปุ่มใบเสนอราคาจึงติดอยู่กับขอบจอตลอด ที่เหลือกดแถบเพื่อกางดู
              (บนจอใหญ่ CSS ซ่อนแถบนี้ แผงยังอยู่ข้างขวาเหมือนเดิม) */}
          <aside className={"cart-side sheet" + (sheet ? " on" : "")}>
            <div className="sum-bar">
              <button className="sum-bar-open" onClick={() => setSheet((v) => !v)} aria-expanded={sheet} aria-controls="sales-summary">
                <span>
                  <small>{sheet ? "แตะเพื่อย่อสรุป" : `ยอดรวมทั้งบิล · ${cart.count} ชิ้น`}</small>
                  <b>{bahtWord(cart.totals?.grand_total ?? cart.subtotal)}</b>
                </span>
                <Icon name={sheet ? "expand_more" : "expand_less"} size={20} />
              </button>
              {/* แถบลอยจอเล็ก: ก่อนบันทึกใบ PRE ปุ่มหลักคือ Save PRE SO · บันทึกแล้วค่อยกลายเป็นใบเสนอราคา */}
              {readyForQuotation(cart) ? (
                <button className="btn primary sum-bar-cta" disabled={busy !== null || cart.items.length === 0} onClick={() => makeQuotation()}>ใบเสนอราคา</button>
              ) : (
                <button className="btn primary sum-bar-cta" disabled={busy !== null || cart.items.length === 0 || !canSavePreso(cart)}
                        title={canSavePreso(cart) ? "" : cart.preso?.message} onClick={() => savePreso()}>Save PRE SO</button>
              )}
            </div>
            <div className="summary" id="sales-summary">
              <h3>สรุปคำสั่งซื้อ</h3>
              <div className="sum-row"><span>สินค้า ({cart.count})</span><b>{bahtWord(cart.subtotal)}</b></div>
              {cart.totals && Number(cart.totals.member_savings) > 0 && <div className="sum-row"><span>ราคาสมาชิก (รวมแล้ว)</span><span className="green">−{bahtWord(cart.totals.member_savings)}</span></div>}
              {cart.totals && cart.totals.lines.length === 0 && (
                <div className="sum-row"><span>ส่วนลด</span><button className="link-btn small" onClick={() => setPromoOpen(true)}>รอเช็คโปร</button></div>
              )}
              {/* ส่วนลดที่เหลือ 0 (หลุดเงื่อนไขแล้ว) ไม่ต้องโชว์ "−0 บาท" — เหตุผลอยู่ในกล่องเตือนข้างล่างแล้ว */}
              {cart.totals?.lines.filter((l) => Number(l.amount) > 0).map((l) => (
                <div key={l.id} className="sum-row"><span>{l.title}{l.status === "pending_approval" ? " (รออนุมัติ)" : ""}</span><span className={l.status === "applied" ? "green" : "muted"}>−{bahtWord(l.amount)}</span></div>
              ))}
              {cart.totals?.warnings.map((w) => (
                <div key={w} className="note warn small">{w}</div>
              ))}
              {/* ค่าขนส่งแยกเป็นบรรทัดตาม Mat ที่เปิดไว้ (เทียร์ / ค่าส่งเพิ่มเติม)
                  ลูกค้าจะได้เห็นว่าเงินก้อนไหนมาจากอะไร ส่วนยอดรวมไปบวกกันที่บรรทัด "ค่าขนส่ง" */}
              {shipLines.map((it) => (
                <div key={it.id} className="sum-row small muted">
                  <span>· {it.name}</span><span>{bahtWord(it.line_total)}</span>
                </div>
              ))}
              {/* ใช้กฎค่าส่งชุดเดียวกับหน้าลูกค้า — ถ้าไม่เข้ากฎข้อไหนเลย ต้องขึ้น "รอประเมิน" เหมือนกัน ห้ามโชว์ 0 บาทเป็นค่าส่งจริง */}
              <div className="sum-row"><span>{shipLines.length > 1 ? "รวมค่าขนส่ง" : "ค่าขนส่ง"}{cart.totals && Number(cart.totals.install_fee) > 0 ? " + ติดตั้ง" : ""}</span>
                {/* พนักงานเปิด Mat ค่าขนส่งไว้ = มีตัวเลขแล้วแม้ยังไม่กรอกที่อยู่ (เทียร์คิดจากยอดบิล
                    ไม่ได้คิดจากปลายทาง) จึงต้องโชว์เลขจริง ไม่ใช่ปุ่ม "รอคำนวณ" */}
                {!cart.totals || (!cart.delivery?.quoted_at && Number(cart.totals.shipping_fee) <= 0) ? (
                  <button className="link-btn small" onClick={() => setDeliveryOpen(true)}>รอคำนวณ</button>
                ) : shipNeedsReview(cart.totals.warnings) ? (
                  <span className="muted">รอเจ้าหน้าที่ประเมิน</span>
                ) : (
                  <b>{bahtWord(Number(cart.totals.shipping_fee) + Number(cart.totals.install_fee) - Number(cart.totals.shipping_discount))}</b>
                )}
              </div>
              {/* โชว์แค่วัน — รอบเช้า/บ่ายทีมคิวจัดส่งเป็นคนซอยเอง พนักงานหน้าร้านไม่ได้เลือก
                  (เบื้องหลังยังจองเป็นรอบอยู่ ใบเสนอราคายังพิมพ์รอบออกไปตามเดิม) */}
              {cart.delivery?.slot_date && <div className="sum-row small muted"><span>คิวจัดส่ง</span><span>{thDate(cart.delivery.slot_date)} · เขต {cart.delivery.zone}</span></div>}
              <div className="sum-total"><span>ยอดรวมทั้งบิล (รวม VAT){shipNeedsReview(cart.totals?.warnings) && <small>ยังไม่รวมค่าจัดส่ง</small>}</span><b>{bahtWord(cart.totals?.grand_total ?? cart.subtotal)}</b></div>
              {/* เช็คลิสต์ตามผังงานหน้าร้าน — ห้าด่านก่อน "ออกใบเสนอราคา"
                  (ใบ PRE เป็นร่าง บันทึกค้างไว้ได้ตลอดแม้ยังไม่ครบ)
                  ด่านที่ยังไม่ถึงคิวจะจาง กดไปทำได้เลยทีละข้อ ไม่ต้องจำลำดับเอง */}
              {cart.preso && (
                <div className={"preso-steps" + (cart.preso.ready ? " ready" : "")}>
                  <div className="preso-head">
                    <b>{cart.preso.ready ? "พร้อมออกใบเสนอราคา" : "ก่อนออกใบเสนอราคา"}</b>
                    <span>{cart.preso.steps.filter((st) => st.ok).length}/{cart.preso.steps.length}</span>
                  </div>
                  {cart.preso.steps.map((st, i) => (
                    <button
                      key={st.key}
                      className={"preso-step" + (st.ok ? " ok" : "") + (st.blocked ? " later" : "")}
                      onClick={() => {
                        if (st.key === "stock") return void checkStock();
                        if (st.key === "promo") return setPromoOpen(true);
                        if (st.key === "delivery") return setDeliveryOpen(true);
                        // ด่าน "ข้อมูลลูกค้า" ขาดได้สองแบบ พาไปคนละที่:
                        //   ยังไม่ผูกลูกค้า -> ไปช่องค้นหาลูกค้า (ชื่อ/เบอร์มาจากทะเบียนลูกค้า)
                        //   ผูกแล้วแต่ขาดที่อยู่ -> ไปบล็อกคิวจัดส่งซึ่งเป็นที่กรอกปลายทาง
                        if (cart.customer) return setDeliveryOpen(true);
                        document.getElementById("sales-customer")?.scrollIntoView({ block: "center" });
                        document.querySelector<HTMLInputElement>("#sales-customer input")?.focus();
                      }}
                    >
                      <span className="preso-num">{st.ok ? <Icon name="check" size={14} /> : i + 1}</span>
                      <span className="preso-txt"><b>{st.title}</b><small>{st.note}</small></span>
                    </button>
                  ))}
                </div>
              )}
              <div className="col" style={{ marginTop: 12 }}>
                {/* เช็คทั้งตะกร้าในการยิงครั้งเดียว — SAP จำลองทั้งบิล บรรทัดแรกกินของก่อน ยิงทีละชิ้นจะเห็นของตัวเดียวกันซ้ำแล้วขายเกิน */}
                <button className="btn block" onClick={checkStock} disabled={busy === "stock" || cart.items.length === 0}>
                  <Icon name="inventory_2" size={18} /> {busy === "stock" ? "กำลังเช็คสต็อก…" : avail ? "เช็คสต็อกอีกครั้ง" : "เช็คสต็อก"}
                </button>
                {avail && avail.cart_id === cart.id && (
                  <div className={"note small " + (availStale ? "warn" : avail.all_ok ? "ok" : "warn")}>
                    {availStale ? "ของในตะกร้าเปลี่ยนหลังเช็คครั้งล่าสุด — กดเช็คใหม่ก่อนยืนยันกับลูกค้า" : avail.message}
                    <div className="tiny muted" style={{ marginTop: 4 }}>
                      ถามวันส่ง {thDate(avail.req_date)} · ลูกค้า {avail.customer_no}{avail.is_walkin ? " (walk-in)" : ""} · เช็คเมื่อ {thTime(avail.checked_at)}
                    </div>
                    {/* บอกให้ชัดว่าเลขมาจากไหน — ตอนรัน mock ของจริงทุกตัวจะขึ้น "ไม่รู้จักรหัสนี้" ซึ่งชวนเข้าใจผิดว่า SAP ตอบแบบนั้น */}
                    {avail.source === "mock" && <div className="tiny" style={{ marginTop: 2, color: "#a12d2d" }}>⚠ ข้อมูลจำลอง (mock) ไม่ได้ยิง SAP จริง — ตั้ง SAP_AVAIL_URL / SAP_API_KEY แล้วรีสตาร์ท backend</div>}
                  </div>
                )}
                <button className="btn block" onClick={() => setPromoOpen(true)} disabled={cart.items.length === 0}><Icon name="sell" size={18} /> {cart.totals && cart.totals.lines.length > 0 ? "แก้ไขโปรโมชั่น / ส่วนลด" : "เช็คโปรโมชั่น"}</button>
                <button className="btn block" onClick={() => setDeliveryOpen((v) => !v)} disabled={cart.items.length === 0}><Icon name="local_shipping" size={18} /> {cart.delivery?.quoted_at ? "แก้ไขคิวจัดส่ง" : "คิวจัดส่ง"}</button>
                {/* ปุ่มสองตัวนี้เปิดเมื่อครบทุกด่าน — ปล่อยให้กดแล้วค่อยเด้ง error คือทำให้เซลล์เสียเวลาเปล่า */}
                <button className="btn block" disabled={busy === "preso" || cart.items.length === 0 || !canSavePreso(cart)}
                        title={canSavePreso(cart) ? "" : cart.preso?.message} onClick={() => savePreso()}>
                  <Icon name="save" size={18} /> {presoNo ? `บันทึกแล้ว · ${presoNo}` : "Save PRE SO"}
                </button>
                {/* ขั้นสุดท้าย — โผล่ต่อเมื่อบันทึกใบ PRE แล้ว ก่อนหน้านั้นยังไม่มีใบให้ออกใบเสนอราคาจาก */}
                {/* แก้ตะกร้าหลังบันทึก = ใบ PRE ที่เซฟไว้เก่าแล้ว ต้องเช็คใหม่แล้วเซฟทับก่อนถึงออกใบได้ */}
                {readyForQuotation(cart) && (
                  <button className="btn primary block" disabled={busy !== null || cart.items.length === 0} onClick={() => makeQuotation()}>
                    <Icon name="description" size={18} /> Create Quotation · สร้างใบเสนอราคา
                  </button>
                )}
              </div>
              <p className="tiny muted" style={{ marginTop: 10 }}>
                {presoNo ? "ใบเสนอราคาจะยืนราคา 7 วัน แล้วส่งต่อให้ระบบหลังบ้าน convert เป็น SO ใน SAP"
                  : cart.preso?.ready ? "ครบทุกด่านแล้ว — บันทึกใบ PRE ได้เลย แล้วปุ่มออกใบเสนอราคาจะขึ้นให้"
                  : "บันทึกใบ PRE เก็บไว้ก่อนได้เลย · ทำเช็คลิสต์ให้ครบเมื่อไร ปุ่มออกใบเสนอราคาถึงจะขึ้น"}
              </p>
              {cart.expires_at && <p className="tiny muted">ตะกร้านี้หมดอายุอัตโนมัติ {thDate(cart.expires_at)} {thTime(cart.expires_at)} (ต่ออายุทุกครั้งที่ใช้งาน)</p>}
            </div>
          </aside>
          {sheet && <div className="scrim" onClick={() => setSheet(false)} />}
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
      {promoOpen && cart && <PromoPanel mode="staff" cart={cart} isStaff onClose={() => setPromoOpen(false)} onCartChange={(c) => sales.setActive(c)} />}
      {/* คิวจัดส่งเปิดเป็นหน้าต่างซ้อน ไม่ใช่แทรกกลางหน้า
          ของเดิมบล็อกนี้โผล่เหนือรายการสินค้า หน้าจอเลยกระโดดและต้องเลื่อนขึ้นไปหาเอง
          ทำเป็นหน้าต่างแล้วตำแหน่งที่พนักงานกำลังดูอยู่ไม่ขยับ และเดินทีละขั้นในหน้าต่างเดียวจบ */}
      {deliveryOpen && cart && (
        <div className="modal-backdrop" onClick={() => setDeliveryOpen(false)}>
          <div className="modal wide" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h2>คิวจัดส่ง · {cart.customer?.name || `ตะกร้า ${cart.no}`}</h2>
              <button className="icon-btn" onClick={() => setDeliveryOpen(false)} aria-label="ปิด"><Icon name="close" /></button>
            </div>
            <DeliveryPanel key={cart.id} cart={cart} defaultPostcode={cart.customer?.default_postcode} defaultAddress={cart.customer?.default_address} onChanged={sales.reloadActive} />
            <button className="btn dark block" style={{ marginTop: 12 }} onClick={() => setDeliveryOpen(false)}>เสร็จแล้ว</button>
          </div>
        </div>
      )}
      {live && <div className="toast" role="status"><Icon name="notifications_active" size={20} /> {live}</div>}
    </main>
  );
}

function SalesRow({ it, busy, plantName, avail, availStale, onPick, onInc, onDec, onRemove, onNote }: { it: CartItem; busy: boolean; plantName: string; avail: AvailabilityItem | null; availStale: boolean; onPick: () => void; onInc: () => void; onDec: () => void; onRemove: () => void; onNote: (n: string) => void }) {
  const [note, setNote] = useState(it.note || "");
  const [noteOpen, setNoteOpen] = useState(!!it.note);
  return (
    <div className={"cart-row sales-row" + (it.selected ? " picked" : " unpicked")}>
      <input type="checkbox" className="cart-pick" checked={it.selected} disabled={busy} onChange={onPick} aria-label="คิดเงินรายการนี้" />
      <Link to={`/p/${it.matnr}`} className="cart-img"><Placeholder src={imageSources(it.matnr, it.image_url)} label="1:1" /></Link>
      <div className="cart-info">
        {/* ป้ายเฉพาะเคสที่ผิดปกติ — "เซลล์เพิ่ม" คือค่าปกติของหน้านี้ ติดไว้ทุกใบก็ไม่ได้บอกอะไร
            มีแต่กินความสูงการ์ด (จอเล็กเลื่อนดูของ 7-8 ชิ้นแล้วเมื่อย) */}
        {it.added_by !== "sales" && (
          <div className="row wrap" style={{ gap: 6, marginBottom: 4 }}>
            <span className="chip light">จากตะกร้าลูกค้า</span>
          </div>
        )}
        <Link to={`/p/${it.matnr}`} className="cart-name">{it.name}</Link>
        {/* รุ่น/ขนาด + วิธีรับของ อยู่บรรทัดเดียวกัน — ของเดิมแยกเป็นป้ายอีกแถวหนึ่งต่างหาก */}
        <div className="small muted cart-meta">
          {[it.variant, it.spec, SUPPLY_LABEL[it.supply_mode] + (it.plant_code ? ` · ${plantName}` : "")].filter(Boolean).join(" · ")}
          {it.atp_date ? ` · ATP ${thDate(it.atp_date)}` : ""}
        </div>
        {/* MATNR คือสิ่งที่เซลล์กวาดตาหาก่อนอย่างอื่นเสมอ (ใช้คุยกับคลัง/SAP) — ทำเป็นป้ายให้เห็นชัด */}
        <div className="mat-code">MATNR <b>{it.matnr}</b>{it.sku && it.sku !== it.matnr ? ` · ${it.sku}` : ""}</div>
        <div className="small muted cart-unit">{bahtWord(it.unit_price)} / ชิ้น</div>
        {/* ผลเช็คของมาจากการยิงทั้งตะกร้าครั้งเดียว (ปุ่มในสรุปคำสั่งซื้อ) — บรรทัดนี้แค่แสดงผลของตัวเอง */}
        {avail && <div className={availStale ? "avail-stale" : undefined}><AvailBadge a={avail} /></div>}
        <form className={"row cart-note" + (noteOpen ? " on" : "")} onSubmit={(e) => { e.preventDefault(); onNote(note); }}>
          <input className="hdr-pop-input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="หมายเหตุ เช่น รอลูกค้าวัดห้อง" />
          <button className="btn sm" type="submit" disabled={busy || note === (it.note || "")}>บันทึก</button>
        </form>
        {/* จอเล็กพับช่องหมายเหตุไว้ก่อน — ส่วนใหญ่ไม่ได้ใส่ ให้กดเปิดเมื่อจะใช้ (จอใหญ่โชว์ตลอด) */}
        <button type="button" className="link-btn small cart-note-add" onClick={() => setNoteOpen(true)}>+ เพิ่มหมายเหตุ</button>
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
        <button className="btn sm sess-act" type="submit" disabled={q.trim().length < 2}>ค้นหา</button>
        <button className="btn sm sess-act" type="button" onClick={() => setQ("094-916-4600")} title="สแกน QR (จำลอง)"><Icon name="qr_code_scanner" size={18} /></button>
      </form>
      {err && <div className="note err small" style={{ marginTop: 6 }}>{err}</div>}
      {hits && (
        <div className="cust-hits">
          {hits.length === 0 && <div className="small">ไม่พบลูกค้า — ลูกค้าใหม่ walk-in ให้ลงทะเบียนด้วย OTP ก่อน</div>}
          {hits.map((h) => (
            <div key={(h.sap_customer_no || "") + (h.email || "")} className="cust-hit">
              <span className="avatar">{h.name.slice(0, 2)}</span>
              <span className="grow">
                <b>{h.name}</b> · {(h.points || 0).toLocaleString()} พ้อยท์
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
  // ไม่มีปุ่มเช็คของรายตัวในหน้าค้นหาแล้ว — เลขที่ได้ยังไม่หักของที่อยู่ในตะกร้า
  // ถามทีละตัวหลายรอบทุกตัวจะเห็นของก้อนเดียวกันเต็มเหมือนกันหมด = ขายเกิน
  // เช็คได้ที่เดียวคือปุ่มเช็คสต็อกในสรุปคำสั่งซื้อ ซึ่งยิงทั้งตะกร้าครั้งเดียว
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
          {items.map((m) => (
              <div key={m.matnr} className="mat-hit">
                <Placeholder src={imageSources(m.matnr, m.image_url)} label="1:1" className="mat-img" />
                <div className="grow">
                  <b>{m.name_th}</b>
                  <div className="small muted">{m.variant}{m.spec ? ` · ${m.spec}` : ""}</div>
                  <div className="mono tiny muted">MATNR {m.matnr}{m.sku && m.sku !== m.matnr ? ` · ${m.sku}` : ""}</div>
                  <div className="row wrap" style={{ gap: 8, marginTop: 4 }}>
                    <b>{baht(m.standard_price)}</b>
                  </div>
                </div>
                <div className="col">
                  <button className="btn dark sm" onClick={() => onAdd(m, m.requires_install ? "install" : store && m.is_takeaway_ok ? "takeaway" : "ship", store && m.is_takeaway_ok && !m.requires_install ? store.plant_code : null)}>ลงตะกร้า</button>
                </div>
              </div>
          ))}
        </div>
      </div>
    </div>
  );
}

type SearchOutLike = { items: MaterialCard[] };
