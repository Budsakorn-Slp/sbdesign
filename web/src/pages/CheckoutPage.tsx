import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AddressBook from "../components/AddressBook";
import DeliveryPanel from "../components/DeliveryPanel";
import Icon from "../components/Icon";
import Placeholder from "../components/Placeholder";
import { imageSources } from "../lib/images";
import PromoPanel from "../components/PromoPanel";
import { apiPost, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useCart } from "../lib/cart";
import { useContent } from "../lib/content";
import { bahtWord } from "../lib/format";
import type { Quotation, SavedAddress } from "../lib/types";

const PAY_METHODS = [
  { key: "card", icon: "credit_card", title: "บัตรเครดิต/เดบิต", note: "Visa, Mastercard, JCB" },
  { key: "qr", icon: "qr_code_2", title: "QR Code Payment", note: "PromptPay, Thai QR" },
  { key: "wallet", icon: "account_balance_wallet", title: "E-Wallet", note: "TrueMoney, LINE Pay" },
  { key: "installment", icon: "schedule", title: "ผ่อน 0% 10 เดือน", note: "เฉพาะบัตรที่ร่วมรายการ" },
];

export default function CheckoutPage() {
  const auth = useAuth();
  const { cart, refresh, setCart } = useCart();
  const { shipTo } = useContent();
  const nav = useNavigate();
  const [pay, setPay] = useState("card");
  const [promoOpen, setPromoOpen] = useState(false);
  const [taxSame, setTaxSame] = useState(true);
  const [placing, setPlacing] = useState(false);
  // จอเล็ก: สรุปใบสั่งซื้อ + วิธีชำระเงิน กลายเป็นแผงลอยจากขอบล่าง แบบเดียวกับหน้าตะกร้า
  const [sheet, setSheet] = useState(false);
  const [orderErr, setOrderErr] = useState<string | null>(null);
  // ที่อยู่จัดส่งมาจากสมุดที่อยู่ — เลือกได้ เปลี่ยนได้ ไม่ต้องพิมพ์ใหม่ทุกครั้ง
  const [ship, setShip] = useState<SavedAddress | null>(null);

  useEffect(() => {
    if (!auth.ready) return;
    if (auth.role !== "customer") nav("/cart");
  }, [auth.ready, auth.role, nav]);

  if (!cart) return <main className="container sec"><div className="ph" style={{ height: 240 }}>กำลังโหลดตะกร้า…</div></main>;

  const placeOrder = async () => {
    setPlacing(true);
    setOrderErr(null);
    try {
      const q = await apiPost<Quotation>("/checkout/quotation", { force: false });
      await refresh();
      nav(`/pay/${q.quotation_no}`);
    } catch (e) {
      const detail = (e as { detail?: { shortages?: { name: string; need: number; available: number }[]; message?: string } }).detail;
      if (detail && typeof detail === "object" && detail.shortages) {
        setOrderErr(`${detail.message} — ${detail.shortages.map((s) => `${s.name} เหลือ ${s.available}`).join(", ")}`);
      } else setOrderErr(errorMessage(e));
    } finally {
      setPlacing(false);
    }
  };
  const t = cart.totals;
  const quoted = Boolean(cart.delivery?.quoted_at);

  return (
    <main className="container sec checkout">
      <Link to="/cart" className="row small muted" style={{ marginBottom: 10 }}><Icon name="arrow_back" size={18} /> กลับไปที่ตะกร้า</Link>
      <div className="checkout-grid has-sheet">
        <div className="checkout-main">
          <h1 className="cart-title">สั่งซื้อสินค้า</h1>
          <section className="card flat">
            <div className="row between" style={{ marginBottom: 4 }}>
              <h3 style={{ margin: 0 }}>ที่อยู่จัดส่ง</h3>
              <span className="small muted">ใช้สำหรับส่งสินค้าเท่านั้น</span>
            </div>
            <p className="small muted" style={{ margin: "2px 0 12px" }}>เลือกที่อยู่ที่บันทึกไว้ หรือเพิ่มใหม่ — เปลี่ยนได้จนกว่าจะกดยืนยันคำสั่งซื้อ</p>
            <AddressBook
              selectedId={ship?.id || null}
              onSelect={setShip}
              defaults={{
                receiver: auth.user?.name || "",
                phone: auth.user?.phone || "",
                address: auth.user?.default_address || "",
                postcode: auth.user?.default_postcode || shipTo?.postcode || "",
                province: shipTo?.name_th || "",
              }}
            />
          </section>

          <section style={{ marginTop: 16 }}>
            {/* ค่าส่งคิดใหม่อัตโนมัติทุกครั้งที่เปลี่ยนที่อยู่ · ลูกค้าไม่ได้เลือกคิวจัดส่งเอง
                ทีมจัดส่งจัดคิวให้ตามพื้นที่แล้วโทรยืนยันวันทีหลัง */}
            <DeliveryPanel
              key={cart.id}
              cart={cart}
              defaultPostcode={ship?.postcode || ""}
              defaultAddress={ship?.one_line || ""}
              onChanged={refresh}
              hideSlots
              autoQuote
            />
            <p className="small muted" style={{ marginTop: 6 }}>
              คิดค่าจัดส่งอัตโนมัติจากรหัสไปรษณีย์และปริมาตรสินค้า · เจ้าหน้าที่จะติดต่อนัดวันจัดส่งหลังยืนยันคำสั่งซื้อ
            </p>
          </section>

          {/* เลือกวิธีชำระเงินบนหน้าเลย ไม่ต้องกางแผงสรุปก่อน — เป็นสิ่งที่ต้องเลือกจริงๆ
              ไม่ใช่ข้อมูลไว้ตรวจทาน ส่วนแผงลอยด้านล่างเหลือแค่สรุปยอดกับปุ่มยืนยัน */}
          <section className="card flat" style={{ marginTop: 16 }}>
            <h3>วิธีการชำระเงิน</h3>
            <div className="col" style={{ marginTop: 8 }}>
              {PAY_METHODS.map((p) => (
                <label key={p.key} className={"opt" + (pay === p.key ? " on" : "")}>
                  <input type="radio" name="pay" checked={pay === p.key} onChange={() => setPay(p.key)} />
                  <Icon name={p.icon} size={22} />
                  <span className="grow">{p.title}<small>{p.note}</small></span>
                  <Icon name="check_circle" size={20} style={{ color: pay === p.key ? "var(--ink)" : "var(--line-2)" }} fill={pay === p.key} />
                </label>
              ))}
            </div>
          </section>

        </div>

        <aside className={"checkout-side cart-side sheet" + (sheet ? " on" : "")}>
          {/* แถบลอย: ปิดอยู่เห็นยอดรวม + ปุ่มยืนยัน · แตะเพื่อกางดูสรุปใบสั่งซื้อ */}
          <div className="sum-bar">
            <button className="sum-bar-open" onClick={() => setSheet((v) => !v)} aria-expanded={sheet} aria-controls="checkout-summary">
              <span>
                <small>{sheet ? "แตะเพื่อย่อสรุป" : `ยอดรวมทั้งหมด · ${cart.count} ชิ้น`}</small>
                <b>{bahtWord(t?.grand_total ?? cart.subtotal)}</b>
              </span>
              <Icon name={sheet ? "expand_more" : "expand_less"} size={20} />
            </button>
            <button className="btn dark sum-bar-cta" disabled={placing || cart.items.length === 0 || !ship || !quoted}
                    title={ship ? (quoted ? "" : "กำลังคิดค่าจัดส่ง…") : "เลือกที่อยู่จัดส่งก่อน"} onClick={placeOrder}>
              {placing ? "กำลังออกใบ…" : "ยืนยันการสั่งซื้อ"}
            </button>
          </div>

          <div className="sheet-body" id="checkout-summary">
          <section className="card flat">
            <h3>สรุปใบสั่งซื้อ</h3>
            {/* ลูกค้าต้องการแค่ "ของอะไร กี่ชิ้น เท่าไร" — รายละเอียดฝั่งระบบ (วิธีรับของ สาขา
                วันที่ ATP) อยู่ในใบสั่งซื้อและหน้าติดตามสถานะอยู่แล้ว */}
            <div className="co-items">
              {cart.items.map((it) => (
                <div key={it.id} className="co-item">
                  <Placeholder src={imageSources(it.matnr, it.image_url)} label="" className="co-item-img" />
                  <div className="grow">
                    <div className="co-item-name">{it.name}{it.variant ? ` ${it.variant}` : ""}</div>
                    <div className="tiny muted">SKU: {it.matnr}</div>
                    <div className="tiny muted">จำนวน: {it.qty}</div>
                  </div>
                  <b className="co-item-price">{bahtWord(it.line_total)}</b>
                </div>
              ))}
            </div>
            <div className="row" style={{ marginTop: 12 }}>
              <button className="btn sm grow" onClick={() => setPromoOpen(true)}><Icon name="sell" size={16} /> {t && t.lines.length ? "แก้ไขโค้ด / โปรโมชั่น" : "ใช้โค้ดส่วนลด / โปรโมชั่น"}</button>
            </div>
            {t && (
              <>
                <div className="sum-row" style={{ marginTop: 8 }}><span>ยอดสั่งซื้อ</span><b>{bahtWord(t.subtotal)}</b></div>
                {t.lines.filter((l) => Number(l.amount) > 0).map((l) => (
                  <div key={l.id} className="sum-row"><span className="green"><Icon name="check_circle" size={14} /> {l.title}</span><span className="green">−{bahtWord(l.amount)}</span></div>
                ))}
                <div className="sum-row"><span>ค่าจัดส่ง{Number(t.install_fee) > 0 ? " + ติดตั้ง" : ""}</span><b>{cart.delivery?.quoted_at ? bahtWord(Number(t.shipping_fee) + Number(t.install_fee) - Number(t.shipping_discount)) : "รอคำนวณ"}</b></div>
                {/* คิวจัดส่งไม่ให้ลูกค้าเลือกแล้ว — เจ้าหน้าที่จัดคิวตามพื้นที่แล้วโทรนัดวันทีหลัง */}
                {/* ตัดบรรทัดแยก VAT ออก — ราคาที่โชว์รวม VAT อยู่แล้ว ตัวเลขแยกไปอยู่ในใบเสร็จ/ใบกำกับภาษี
                    ลูกค้าหน้าจ่ายเงินต้องการรู้แค่ยอดที่ต้องจ่ายจริง */}
                <div className="sum-total"><span>ยอดสั่งซื้อทั้งหมด</span><b>{bahtWord(t.grand_total)}</b></div>
              </>
            )}
            <label className="row small" style={{ marginTop: 10 }}><input type="checkbox" checked={taxSame} onChange={(e) => setTaxSame(e.target.checked)} /> ที่อยู่สำหรับออกใบเสร็จจะใช้ที่อยู่ผู้รับสินค้า</label>
            {orderErr && <div className="note err small" style={{ marginTop: 10 }}>{orderErr}</div>}
            {!ship && <div className="note small" style={{ marginTop: 10 }}>เลือกที่อยู่จัดส่งก่อน ระบบถึงจะคิดค่าจัดส่งให้ได้</div>}
            <button className="btn dark lg block square" style={{ marginTop: 12 }} disabled={placing || cart.items.length === 0 || !ship || !quoted}
                    title={ship ? (quoted ? "" : "กำลังคิดค่าจัดส่ง…") : "เลือกที่อยู่จัดส่งก่อน"} onClick={placeOrder}>
              {placing ? "กำลังออกใบสั่งซื้อ…" : "ยืนยันการสั่งซื้อ"}
            </button>
          </section>
          </div>
        </aside>
        {/* กางแผงอยู่แล้วแตะนอกแผง = ย่อกลับ (จอใหญ่ CSS ซ่อนฉากหลังนี้) */}
        {sheet && <div className="scrim" onClick={() => setSheet(false)} />}
      </div>
      {promoOpen && <PromoPanel cart={cart} isStaff={false} onClose={() => setPromoOpen(false)} onCartChange={setCart} />}
    </main>
  );
}
