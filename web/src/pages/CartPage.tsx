import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Icon from "../components/Icon";
import Placeholder from "../components/Placeholder";
import PromoPanel from "../components/PromoPanel";
import { apiPost, errorMessage } from "../lib/api";
import { ROLE_PERMS, useAuth } from "../lib/auth";
import { useCart } from "../lib/cart";
import { useContent } from "../lib/content";
import { bahtWord, thTime } from "../lib/format";
import { useCartSocket } from "../lib/realtime";
import type { CartItem } from "../lib/types";

export default function CartPage() {
  const auth = useAuth();
  const { cart, loading, error, update, remove, ack, select, refresh, setCart } = useCart();
  const { plants } = useContent();
  const nav = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [live, setLive] = useState<string | null>(null);
  const [promoOpen, setPromoOpen] = useState(false);

  // realtime: เซลล์เพิ่ม/แก้ของ → รีเฟรชทันที + เด้งข้อความ
  useCartSocket(cart?.id, (evt) => {
    if (evt.type === "hello") return;
    refresh();
    if (evt.type === "item_added" && evt.added_by === "sales") setLive(`${evt.by_name || "พนักงานขาย"} เพิ่มสินค้าให้คุณ 1 รายการ — ตรวจสอบด้านล่าง`);
    else if (evt.type === "customer_attached") setLive(`${evt.sales_name || "พนักงานขาย"} เริ่มช่วยดูแลตะกร้าของคุณ`);
    else if (evt.type === "session_closed") setLive("พนักงานขายจบการดูแลตะกร้านี้แล้ว — ตะกร้ายังเป็นของคุณ");
  });
  useEffect(() => {
    if (!live) return;
    const t = setTimeout(() => setLive(null), 6000);
    return () => clearTimeout(t);
  }, [live]);

  if (auth.role === "sales" || auth.role === "manager") {
    return (
      <main className="container sec">
        <div className="card">
          <b>โหมดพนักงานขาย</b> — ตะกร้าของลูกค้าจัดการที่หน้า <Link to="/sales" className="strong">ตะกร้าที่กำลังดูแล</Link> (STEP 4)
        </div>
      </main>
    );
  }

  const plantName = (code: string | null) => plants.find((p) => p.plant_code === code)?.name || code || "";
  const items = cart?.items || [];
  const pending = items.filter((it) => it.pending_ack);
  const canPay = auth.role === "customer";

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

  // ติ๊ก = เก็บที่ฝั่งเซิร์ฟเวอร์ (cart_items.selected) เพราะยอดรวม ส่วนลด ค่าส่ง และการชำระเงินคิดจากรายการที่ติ๊กเท่านั้น
  const picked = items.filter((it) => it.selected).map((it) => it.id);
  const allPicked = items.length > 0 && picked.length === items.length;
  const togglePick = (it: CartItem) => run(it.id, () => select([it.id], !it.selected));
  const toggleAll = () => run("bulk", () => select(null, !allPicked));
  const removePicked = () =>
    run("bulk", async () => {
      for (const id of picked) await remove(id);
    });

  const checkout = () =>
    run("checkout", async () => {
      await apiPost("/cart/checkout-check");
      nav("/checkout");
    });

  return (
    <main className="container sec cart">
      <Link to="/search" className="row small muted" style={{ marginBottom: 10 }}><Icon name="arrow_back" size={18} /> กลับไปช้อปต่อ</Link>
      <h1 className="cart-title">ตะกร้าสินค้าของคุณ</h1>

      <div className="cart-grid">
        <div className="cart-main">
          {auth.role === "guest" && (
            <div className="banner guest">
              <Icon name="lock" size={22} />
              <div className="grow">
                คุณยังไม่ได้เข้าสู่ระบบ — เพิ่ม/ลบสินค้าในตะกร้าได้ แต่ต้องเข้าสู่ระบบก่อนชำระเงิน หรือให้พนักงานขายช่วยดูแลตะกร้านี้
                <div style={{ marginTop: 8 }}><button className="btn dark sm" onClick={auth.openLogin}>เข้าสู่ระบบ / ลงทะเบียน</button></div>
              </div>
            </div>
          )}
          {auth.role === "customer" && auth.user && (
            <div className="banner ok">
              <Icon name="verified_user" size={22} />
              <div className="grow">เข้าสู่ระบบแล้ว — ใช้ราคาสมาชิก {auth.user.tier || ""} และชำระเงินได้ทันที</div>
            </div>
          )}
          {cart?.owner_sales && (
            <div className="banner sales">
              <Icon name="support_agent" size={22} />
              <div className="grow">
                <b>{cart.owner_sales.name}</b> กำลังช่วยดูแลตะกร้านี้ · สาขา{plantName(cart.owner_sales.branch_id)} · SESSION {cart.no}
              </div>
            </div>
          )}

          {pending.length > 0 && (
            <div className="pending-card">
              <div className="row"><Icon name="add_shopping_cart" size={22} /> <b>พนักงานเพิ่มสินค้าให้คุณ {pending.length} รายการ</b></div>
              <p className="small muted" style={{ margin: "4px 0 10px" }}>คุณเลือกได้ว่าจะเก็บไว้หรือลบออก</p>
              {pending.map((it) => (
                <div key={it.id} className="pending-row">
                  <Placeholder ratio="1 / 1" label="1:1" className="pending-img" />
                  <div className="grow">
                    <b>{it.name}</b>
                    <div className="small muted">{it.variant} · {bahtWord(it.unit_price)} × {it.qty}</div>
                    <div className="tiny muted">เพิ่มโดย {it.added_by_name || "พนักงานขาย"}{it.added_by_code ? ` (${it.added_by_code})` : ""} · {thTime(it.added_at)}</div>
                  </div>
                  <div className="row">
                    <button className="btn dark sm" disabled={busy === it.id} onClick={() => run(it.id, () => ack(it.id))}>เก็บไว้</button>
                    <button className="btn sm" disabled={busy === it.id} onClick={() => run(it.id, () => remove(it.id))}>ลบออก</button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {msg && <div className="note err" style={{ marginBottom: 12 }}>{msg}</div>}
          {error && <div className="note err" style={{ marginBottom: 12 }}>{error}</div>}

          {!cart && loading && <div className="ph" style={{ height: 200 }}>กำลังโหลดตะกร้า…</div>}

          {cart && items.length === 0 && (
            <div className="cart-empty">
              <Icon name="shopping_cart" size={48} />
              <div className="strong">ยังไม่มีสินค้าในตะกร้า</div>
              <Link to="/search" className="btn dark">เลือกซื้อสินค้า</Link>
            </div>
          )}

          {cart && items.length > 0 && (
            <>
              <p className="cart-intro">สินค้ากำลังรอคุณอยู่ในตะกร้าทั้งหมด {cart.all_count} ชิ้น ชำระเงินง่าย ๆ อีกเพียงไม่กี่ขั้นตอน เลือกใช้บริการจัดส่งแล้วรอรับสินค้าที่บ้านได้เลย!</p>
              <div className="cart-bulk">
                <label className="row small">
                  <input type="checkbox" className="cart-pick" checked={allPicked} disabled={busy === "bulk"} onChange={toggleAll} aria-label="เลือกทั้งหมด" />
                  เลือกทั้งหมด{picked.length > 0 ? ` (เลือกแล้ว ${picked.length} รายการ)` : ""}
                </label>
                <button className="link-btn" disabled={!picked.length || busy === "bulk"} onClick={removePicked}>
                  <Icon name="delete" size={16} /> ลบที่เลือก
                </button>
              </div>
              <div className="cart-items">
                {items.map((it) => (
                  <CartRow key={it.id} it={it} busy={busy === it.id || busy === "bulk"} picked={it.selected} onPick={() => togglePick(it)}
                    onInc={() => run(it.id, () => update(it.id, { qty: it.qty + 1 }))}
                    onDec={() => it.qty > 1 && run(it.id, () => update(it.id, { qty: it.qty - 1 }))}
                    onRemove={() => run(it.id, () => remove(it.id))} />
                ))}
              </div>
              {/* ช่องล่างสุด: ยอดรวมของรายการที่ติ๊กไว้ทั้งหมด */}
              <div className="cart-foot">
                <span>ยอดรวมสินค้าที่เลือก ({cart.count} ชิ้น)</span>
                <b>{bahtWord(cart.subtotal)}</b>
              </div>
            </>
          )}
        </div>

        <aside className="cart-side">
          <div className="summary">
            <h3>สรุปคำสั่งซื้อ</h3>
            <div className="sum-row"><span>สินค้า ({cart?.count || 0})</span><b>{bahtWord(cart?.subtotal || 0)}</b></div>
            {/* ยอดทั้งหมดคิดจากรายการที่ติ๊กเท่านั้น ของที่ไม่ติ๊กยังอยู่ในตะกร้า */}
            {!!cart && cart.item_count > cart.selected_count && (
              <div className="sum-row small muted"><span>ไม่ได้เลือก {cart.item_count - cart.selected_count} รายการ</span><span>ไม่คิดยอดรอบนี้</span></div>
            )}
            {cart?.totals?.lines.map((l) => (
              <div key={l.id} className="sum-row"><span>{l.title}{l.status === "pending_approval" ? " (รออนุมัติ)" : ""}</span><span className={l.status === "applied" ? "green" : "muted"}>−{bahtWord(l.amount)}</span></div>
            ))}
            {/* ปุ่มเต็มความกว้าง ให้เห็นชัดว่ากดได้ — ในแผงมีทั้งโปรที่เข้าเงื่อนไขให้กดใช้ และช่องกรอกโค้ดเอง */}
            <button className="btn block promo-btn" disabled={!items.length} onClick={() => setPromoOpen(true)}>
              <Icon name="local_offer" size={18} />
              {cart?.totals && cart.totals.lines.length ? "แก้ไขโปรโมชั่น / โค้ดส่วนลด" : "เช็คโปรโมชั่น หรือกรอกโค้ดส่วนลด"}
            </button>
            <div className="sum-row"><span>ราคาค่าจัดส่ง</span><span className="muted">เริ่มต้น 350 บาท</span></div>
            <div className="sum-row"><span className="muted"><i>หรือ</i> <u>ใช้บริการรับที่สาขา</u></span><span className="muted">ไม่มีค่าบริการ</span></div>
            <div className="sum-total">
              <span>ยอดรวม<small>ไม่รวมค่าประกอบสินค้า</small></span>
              <b>{bahtWord(cart?.totals?.net_total ?? cart?.subtotal ?? 0)}</b>
            </div>
            <p className="tiny muted">เมื่อคลิก "ชำระเงิน" แสดงว่าคุณยอมรับ <u>นโยบายความเป็นส่วนตัว</u></p>
            {canPay ? (
              <button className="btn primary lg block" disabled={!cart?.selected_count || busy === "checkout"} onClick={checkout}>
                ชำระเงิน{cart?.selected_count ? ` (${cart.selected_count} รายการ)` : ""}
              </button>
            ) : (
              <button className="btn dark lg block" onClick={auth.openLogin}><Icon name="lock" size={18} /> เข้าสู่ระบบเพื่อชำระเงิน</button>
            )}
            <div className="pay-icons">
              {["VISA", "MC", "PromptPay", "TrueMoney", "LINE Pay", "ผ่อน 0%"].map((p) => (
                <span key={p} className="ftr-pay mono">{p}</span>
              ))}
            </div>
            <div className="row small" style={{ marginTop: 12 }}><Icon name="volunteer_activism" size={18} /> <u>365 วันในการเปลี่ยนความคิดของคุณ</u></div>
          </div>

          {live && <div className="toast" role="status"><Icon name="notifications_active" size={20} /> {live}</div>}
          {promoOpen && cart && <PromoPanel cart={cart} isStaff={false} onClose={() => setPromoOpen(false)} onCartChange={setCart} />}
          <div className="card flat" style={{ marginTop: 14 }}>
            <div className="small muted">สิทธิ์ของบัญชีที่ใช้อยู่ · {auth.user ? `${auth.user.name}${auth.user.tier ? " · สมาชิก " + auth.user.tier : ""}` : "ผู้เยี่ยมชม (ไม่ล็อกอิน)"}</div>
            <ul className="perm-list">
              {ROLE_PERMS[auth.role].map((p) => (
                <li key={p.label} className={p.ok ? "ok" : "no"}><Icon name={p.ok ? "check_circle" : "block"} size={16} /> {p.label}</li>
              ))}
            </ul>
          </div>
        </aside>
      </div>
    </main>
  );
}

function CartRow({ it, busy, picked, onPick, onInc, onDec, onRemove }: { it: CartItem; busy: boolean; picked: boolean; onPick: () => void; onInc: () => void; onDec: () => void; onRemove: () => void }) {
  return (
    <div className={"cart-row" + (picked ? " picked" : "")}>
      {/* หัวแถว: ติ๊กเลือก · รูป · ชื่อ+รหัส · ปุ่มแก้ไข/ลบ */}
      <div className="cart-row-head">
        <input type="checkbox" className="cart-pick" checked={picked} disabled={busy} onChange={onPick} aria-label={`เลือก ${it.name}`} />
        <Link to={`/p/${it.matnr}`} className="cart-img"><Placeholder src={it.image_url} label="1:1" /></Link>
        <div className="cart-info">
          {it.added_by === "sales" && (
            <div className="staff-tag"><Icon name="support_agent" size={14} /> พนักงานเพิ่มให้ · {it.added_by_name || "พนักงานขาย"}{it.added_by_code ? ` (${it.added_by_code})` : ""} · {thTime(it.added_at)}</div>
          )}
          <Link to={`/p/${it.matnr}`} className="cart-name">{it.name}</Link>
          {it.variant && <div className="small muted">{it.variant}</div>}
          {it.spec && <div className="small muted">{it.spec}</div>}
          <div className="cart-code">รหัสสินค้า: {it.matnr}</div>
          {it.note && <div className="small muted">หมายเหตุ: {it.note}</div>}
        </div>
        <div className="cart-tools">
          {/* วิธีรับสินค้า (ส่ง/ยกกลับ/ติดตั้ง) ย้ายไปเลือกทีเดียวที่หน้าชำระเงิน — ตรงนี้เลยเหลือแค่แก้ไขกับลบ */}
          <Link to={`/p/${it.matnr}`} className="icon-btn edit" title="แก้ไขรายการ" aria-label="แก้ไขรายการ"><Icon name="edit" size={18} /></Link>
          <button className="icon-btn danger" onClick={onRemove} disabled={busy} title="ลบออกจากตะกร้า" aria-label="ลบออกจากตะกร้า"><Icon name="delete" size={18} /></button>
        </div>
      </div>

      {/* ท้ายแถว: ราคา · จำนวน ชิดขวา (ยอดรวมรายบรรทัดตัดออก เพราะเท่ากับราคา × จำนวนที่เห็นอยู่แล้ว — ไปดูรวมทั้งหมดที่ช่องล่างสุด) */}
      <div className="cart-row-cols">
        <div className="cart-col">
          <span className="cart-col-lbl">ราคา</span>
          <b>{bahtWord(it.unit_price)}</b>
          {it.price_tier !== "standard" && <span className="tiny muted">ราคาสมาชิก {it.price_tier}</span>}
        </div>
        <div className="cart-col center">
          <span className="cart-col-lbl">จำนวน</span>
          <div className="qty sm">
            <button onClick={onDec} disabled={busy || it.qty <= 1} aria-label="ลด"><Icon name="remove" size={16} /></button>
            <span>{it.qty}</span>
            <button onClick={onInc} disabled={busy} aria-label="เพิ่ม"><Icon name="add" size={16} /></button>
          </div>
        </div>
      </div>
    </div>
  );
}
