import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AddressPicker from "../components/AddressPicker";
import DeliveryPanel from "../components/DeliveryPanel";
import Icon from "../components/Icon";
import Placeholder from "../components/Placeholder";
import PromoPanel from "../components/PromoPanel";
import { apiPost, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useCart } from "../lib/cart";
import { useContent } from "../lib/content";
import { bahtWord, thDate } from "../lib/format";
import type { Quotation } from "../lib/types";

const PAY_METHODS = [
  { key: "card", icon: "credit_card", title: "บัตรเครดิต/เดบิต", note: "Visa, Mastercard, JCB" },
  { key: "qr", icon: "qr_code_2", title: "QR Code Payment", note: "PromptPay, Thai QR" },
  { key: "wallet", icon: "account_balance_wallet", title: "E-Wallet", note: "TrueMoney, LINE Pay" },
  { key: "installment", icon: "schedule", title: "ผ่อน 0% 10 เดือน", note: "เฉพาะบัตรที่ร่วมรายการ" },
];

type Addr = { email: string; first: string; last: string; phone: string; address: string; street: string; soi: string; sub: string; district: string; province: string; postcode: string };

export default function CheckoutPage() {
  const auth = useAuth();
  const { cart, refresh, setCart } = useCart();
  const { shipTo } = useContent();
  const nav = useNavigate();
  const [pay, setPay] = useState("card");
  const [promoOpen, setPromoOpen] = useState(false);
  const [taxSame, setTaxSame] = useState(true);
  const [placing, setPlacing] = useState(false);
  const [orderErr, setOrderErr] = useState<string | null>(null);
  const [addr, setAddr] = useState<Addr>({ email: "", first: "", last: "", phone: "", address: "", street: "", soi: "", sub: "", district: "", province: "", postcode: "" });

  useEffect(() => {
    if (!auth.ready) return;
    if (auth.role !== "customer") nav("/cart");
  }, [auth.ready, auth.role, nav]);

  useEffect(() => {
    if (!auth.user) return;
    const [first, ...rest] = auth.user.name.split(" ");
    setAddr((a) => ({ ...a, email: auth.user!.email || "", first, last: rest.join(" "), phone: auth.user!.phone || "", address: auth.user!.default_address || "", postcode: auth.user!.default_postcode || a.postcode }));
  }, [auth.user]);

  // จังหวัดที่เลือกไว้บน nav = จุดตั้งต้นของที่อยู่ (AddressPicker จะไล่ย้อนจากรหัสนี้ต่อเอง)
  useEffect(() => {
    if (shipTo?.postcode) setAddr((a) => (a.postcode ? a : { ...a, postcode: shipTo.postcode, province: shipTo.name_th }));
  }, [shipTo]);

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
  const set = (k: keyof Addr) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setAddr({ ...addr, [k]: e.target.value });
  const fullAddress = [addr.address, addr.street && `ถ.${addr.street}`, addr.soi && `ซ.${addr.soi}`, addr.sub, addr.district, addr.province].filter(Boolean).join(" ");

  return (
    <main className="container sec checkout">
      <Link to="/cart" className="row small muted" style={{ marginBottom: 10 }}><Icon name="arrow_back" size={18} /> กลับไปที่ตะกร้า</Link>
      <div className="checkout-grid">
        <div className="checkout-main">
          <h1 className="cart-title">สั่งซื้อสินค้า</h1>
          <section className="card flat">
            <h3>ที่อยู่จัดส่ง</h3>
            <p className="small muted" style={{ margin: "2px 0 12px" }}>*กรุณากรอกข้อมูลให้ครบถ้วน เพื่อความรวดเร็วในการจัดส่งสินค้า</p>
            <div className="form-grid">
              <label className="field span2"><span>อีเมล (E-mail) *</span><input value={addr.email} onChange={set("email")} placeholder="กรอกอีเมล" /></label>
              <label className="field"><span>ชื่อ (First Name) *</span><input value={addr.first} onChange={set("first")} placeholder="กรอกชื่อ" /></label>
              <label className="field"><span>นามสกุล (Last Name) *</span><input value={addr.last} onChange={set("last")} placeholder="กรอกนามสกุล" /></label>
              <label className="field"><span>เบอร์โทรศัพท์ (Phone) *</span><input value={addr.phone} onChange={set("phone")} placeholder="08X-XXX-XXXX" /></label>
              <label className="field"><span>ที่อยู่ (Address) *</span><input value={addr.address} onChange={set("address")} placeholder="เลขที่, หมู่บ้าน/โครงการ/คอนโด, ตึก" /></label>
              <label className="field"><span>ถนน *</span><input value={addr.street} onChange={set("street")} placeholder="เช่น พระราม 9" /></label>
              <label className="field"><span>ซอย (Soi)</span><input value={addr.soi} onChange={set("soi")} placeholder="เช่น พระราม 9 ซอย 41" /></label>
              <AddressPicker
                postcode={addr.postcode}
                sub={addr.sub}
                district={addr.district}
                province={addr.province}
                onChange={(p) => setAddr((a) => ({ ...a, ...(p.postcode !== undefined && { postcode: p.postcode }), ...(p.sub !== undefined && { sub: p.sub }), ...(p.district !== undefined && { district: p.district }), ...(p.province !== undefined && { province: p.province }) }))}
              />
              <label className="field span2"><span>ประเทศ (Country) *</span><select defaultValue="TH"><option value="TH">ไทย</option></select></label>
            </div>
          </section>

          <section style={{ marginTop: 16 }}>
            <DeliveryPanel key={cart.id} cart={cart} defaultPostcode={addr.postcode} defaultAddress={fullAddress} onChanged={refresh} />
            <p className="small muted" style={{ marginTop: 6 }}>คิดค่าจัดส่งอัตโนมัติจากรหัสไปรษณีย์และปริมาตรสินค้า · หรือเลือก "ยกกลับ/รับที่สาขา" รายชิ้นได้จากหน้าสินค้า (ไม่มีค่าบริการ)</p>
          </section>
        </div>

        <aside className="checkout-side">
          <section className="card flat">
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

          <section className="card flat" style={{ marginTop: 14 }}>
            <h3>สรุปใบสั่งซื้อ</h3>
            <div className="col" style={{ marginTop: 8 }}>
              {cart.items.map((it) => (
                <div key={it.id} className="row" style={{ alignItems: "flex-start" }}>
                  <Placeholder src={it.image_url} label="1:1" style={{ width: 48, flex: "none" }} />
                  <div className="grow small">
                    <b>{it.name}</b> <span className="muted">{it.variant}</span>
                    {/* เลขเดียวพอ — SKU กับ MATNR เป็นเลขเดียวกันเกือบทั้งฐาน โชว์สองอันมีแต่ทำให้สับสน */}
                    <div className="muted tiny">MATNR {it.matnr} · จำนวน: {it.qty}</div>
                  </div>
                  <b className="small">{bahtWord(it.line_total)}</b>
                </div>
              ))}
            </div>
            <div className="row" style={{ marginTop: 12 }}>
              <button className="btn sm grow" onClick={() => setPromoOpen(true)}><Icon name="sell" size={16} /> {t && t.lines.length ? "แก้ไขโค้ด / โปรโมชั่น" : "ใช้โค้ดส่วนลด / โปรโมชั่น"}</button>
            </div>
            {t && (
              <>
                <div className="sum-row" style={{ marginTop: 8 }}><span>ยอดสั่งซื้อ</span><b>{bahtWord(t.subtotal)}</b></div>
                {t.lines.map((l) => (
                  <div key={l.id} className="sum-row"><span className="green"><Icon name="check_circle" size={14} /> {l.title}</span><span className="green">−{bahtWord(l.amount)}</span></div>
                ))}
                <div className="sum-row"><span>ค่าจัดส่ง{Number(t.install_fee) > 0 ? " + ติดตั้ง" : ""}</span><b>{cart.delivery?.quoted_at ? bahtWord(Number(t.shipping_fee) + Number(t.install_fee) - Number(t.shipping_discount)) : "รอคำนวณ"}</b></div>
                {cart.delivery?.slot_date && <div className="sum-row small muted"><span>คิวจัดส่ง</span><span>{thDate(cart.delivery.slot_date)} {cart.delivery.slot_period === "am" ? "รอบเช้า" : "รอบบ่าย"}</span></div>}
                <div className="sum-total"><span>ยอดรวมทั้งหมด</span><b>{bahtWord(t.grand_total)}</b></div>
                <div className="tiny muted">รวมภาษีมูลค่าเพิ่ม 7% = {bahtWord(t.vat_included)}</div>
              </>
            )}
            <label className="row small" style={{ marginTop: 10 }}><input type="checkbox" checked={taxSame} onChange={(e) => setTaxSame(e.target.checked)} /> ที่อยู่สำหรับออกใบเสร็จจะใช้ที่อยู่ผู้รับสินค้า</label>
            {orderErr && <div className="note err small" style={{ marginTop: 10 }}>{orderErr}</div>}
            <button className="btn dark lg block square" style={{ marginTop: 12 }} disabled={placing || cart.items.length === 0 || !cart.delivery?.quoted_at} title={cart.delivery?.quoted_at ? "" : "กรุณาคำนวณค่าจัดส่งก่อน"} onClick={placeOrder}>
              {placing ? "กำลังออกใบสั่งซื้อ…" : "ยืนยันการสั่งซื้อ"}
            </button>
          </section>
        </aside>
      </div>
      {promoOpen && <PromoPanel cart={cart} isStaff={false} onClose={() => setPromoOpen(false)} onCartChange={setCart} />}
    </main>
  );
}
