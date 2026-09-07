import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Icon from "../components/Icon";
import Placeholder from "../components/Placeholder";
import { apiPost, errorMessage } from "../lib/api";
import { ROLE_PERMS, useAuth } from "../lib/auth";
import { SUPPLY_LABEL, useCart } from "../lib/cart";
import { useContent } from "../lib/content";
import { bahtWord, thTime } from "../lib/format";
import type { CartItem } from "../lib/types";

export default function CartPage() {
  const auth = useAuth();
  const { cart, loading, error, update, remove, ack } = useCart();
  const { plants } = useContent();
  const nav = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

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
              <p className="cart-intro">สินค้ากำลังรอคุณอยู่ในตะกร้าทั้งหมด {cart.count} ชิ้น ชำระเงินง่าย ๆ อีกเพียงไม่กี่ขั้นตอน เลือกใช้บริการจัดส่งแล้วรอรับสินค้าที่บ้านได้เลย!</p>
              <div className="cart-items">
                {items.map((it) => (
                  <CartRow key={it.id} it={it} busy={busy === it.id} plantName={plantName(it.plant_code)}
                    onInc={() => run(it.id, () => update(it.id, { qty: it.qty + 1 }))}
                    onDec={() => it.qty > 1 && run(it.id, () => update(it.id, { qty: it.qty - 1 }))}
                    onRemove={() => run(it.id, () => remove(it.id))} />
                ))}
              </div>
            </>
          )}
        </div>

        <aside className="cart-side">
          <div className="summary">
            <h3>สรุปคำสั่งซื้อ</h3>
            <div className="sum-row"><span>สินค้า ({cart?.count || 0})</span><b>{bahtWord(cart?.subtotal || 0)}</b></div>
            <div className="sum-row"><span>ราคาค่าจัดส่ง</span><span className="muted">เริ่มต้น 350 บาท</span></div>
            <div className="sum-row"><span className="muted"><i>หรือ</i> <u>ใช้บริการรับที่สาขา</u></span><span className="muted">ไม่มีค่าบริการ</span></div>
            <div className="sum-total">
              <span>ยอดรวม (ไม่รวมค่าประกอบสินค้า)</span>
              <b>{bahtWord(cart?.subtotal || 0)}</b>
            </div>
            <p className="tiny muted">เมื่อคลิก "ชำระเงิน" แสดงว่าคุณยอมรับ <u>นโยบายความเป็นส่วนตัว</u></p>
            {canPay ? (
              <button className="btn primary lg block" disabled={!items.length || busy === "checkout"} onClick={checkout}>ชำระเงิน</button>
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

function CartRow({ it, busy, plantName, onInc, onDec, onRemove }: { it: CartItem; busy: boolean; plantName: string; onInc: () => void; onDec: () => void; onRemove: () => void }) {
  return (
    <div className="cart-row">
      <Link to={`/p/${it.matnr}`} className="cart-img"><Placeholder src={it.image_url} label="1:1" /></Link>
      <div className="cart-info">
        {it.added_by === "sales" && (
          <div className="staff-tag"><Icon name="support_agent" size={14} /> พนักงานเพิ่มให้ · {it.added_by_name || "พนักงานขาย"}{it.added_by_code ? ` (${it.added_by_code})` : ""} · {thTime(it.added_at)}</div>
        )}
        <Link to={`/p/${it.matnr}`} className="cart-name">{it.name}</Link>
        <div className="small muted">{it.variant}</div>
        {it.spec && <div className="small muted">{it.spec}</div>}
        <div className="small muted" style={{ marginTop: 4 }}>{bahtWord(it.unit_price)} / ชิ้น{it.price_tier !== "standard" ? ` · ราคาสมาชิก ${it.price_tier}` : ""}</div>
        <div className="row wrap" style={{ marginTop: 4, gap: 6 }}>
          <span className="pill"><Icon name={it.supply_mode === "takeaway" ? "shopping_bag" : it.supply_mode === "install" ? "handyman" : "local_shipping"} size={14} /> {SUPPLY_LABEL[it.supply_mode] || it.supply_mode}{it.plant_code ? ` · ${plantName}` : ""}</span>
          {it.note && <span className="pill">หมายเหตุ: {it.note}</span>}
        </div>
        <div className="cart-ctrl">
          <div className="qty">
            <button onClick={onDec} disabled={busy || it.qty <= 1} aria-label="ลด"><Icon name="remove" size={18} /></button>
            <span>{it.qty}</span>
            <button onClick={onInc} disabled={busy} aria-label="เพิ่ม"><Icon name="add" size={18} /></button>
          </div>
          <button className="link-btn" onClick={onRemove} disabled={busy}>ลบ</button>
          <button className="link-btn" disabled title="รายการโปรดจะเปิดใช้ใน STEP 10">ย้ายไปที่รายการโปรด</button>
        </div>
      </div>
      <div className="cart-line strong">{bahtWord(it.line_total)}</div>
    </div>
  );
}
