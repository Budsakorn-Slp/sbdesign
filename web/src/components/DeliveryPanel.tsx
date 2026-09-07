import { useEffect, useState, type FormEvent } from "react";
import { apiPost, errorMessage } from "../lib/api";
import { useContent } from "../lib/content";
import { bahtWord, thDate } from "../lib/format";
import type { Cart, DeliveryQuote, DeliverySlot } from "../lib/types";
import Icon from "./Icon";

type Props = {
  cart: Cart;
  defaultPostcode?: string | null;
  defaultAddress?: string | null;
  onChanged: () => Promise<void> | void;
  compact?: boolean;
};

/** S4 · ค่าขนส่งตามเขต + แยกกลุ่ม ยกกลับ/ส่ง/ติดตั้ง + จองคิวจัดส่ง (hold 15 นาที) */
export default function DeliveryPanel({ cart, defaultPostcode, defaultAddress, onChanged, compact }: Props) {
  const { plants } = useContent();
  const [postcode, setPostcode] = useState(cart.delivery?.postcode || defaultPostcode || "");
  const [address, setAddress] = useState(cart.delivery?.address || defaultAddress || "");
  const [quote, setQuote] = useState<DeliveryQuote | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const needsShip = cart.items.some((it) => it.supply_mode === "ship" || it.supply_mode === "install");

  const doQuote = async (e?: FormEvent) => {
    e?.preventDefault();
    setBusy("quote");
    setErr(null);
    try {
      setQuote(await apiPost<DeliveryQuote>("/delivery/quote", { cart_id: cart.id, postcode: postcode.trim(), address: address || null }));
      await onChanged();
    } catch (e2) {
      setErr(errorMessage(e2));
    } finally {
      setBusy(null);
    }
  };

  // ถ้าตะกร้ามี quote อยู่แล้ว โหลด slot มาโชว์ทันที
  useEffect(() => {
    if (cart.delivery?.postcode && !quote && postcode === cart.delivery.postcode) doQuote();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cart.id]);

  const hold = async (slotId: string) => {
    setBusy(slotId);
    setErr(null);
    try {
      await apiPost(`/delivery/slots/${slotId}/hold`, { cart_id: cart.id });
      setQuote(await apiPost<DeliveryQuote>("/delivery/quote", { cart_id: cart.id, postcode: postcode.trim(), address: address || null }));
      await onChanged();
    } catch (e2) {
      setErr(errorMessage(e2));
    } finally {
      setBusy(null);
    }
  };

  const plantName = (code: string | null) => plants.find((p) => p.plant_code === code)?.name || code || "สาขา";
  const byDate = new Map<string, DeliverySlot[]>();
  quote?.slots.forEach((s) => byDate.set(s.date, [...(byDate.get(s.date) || []), s]));

  return (
    <div className={"card flat" + (compact ? " compact" : "")}>
      <div className="row between wrap" style={{ marginBottom: 8 }}>
        <b><Icon name="local_shipping" size={18} /> ค่าขนส่ง + คิวจัดส่ง</b>
        {cart.delivery?.quoted_at && <span className="small muted">เขต {cart.delivery.zone} · {cart.delivery.zone_name}</span>}
      </div>
      <form className="row wrap" onSubmit={doQuote} style={{ gap: 8 }}>
        <Icon name="place" size={20} />
        <input className="hdr-pop-input" style={{ flex: 2, minWidth: 220 }} value={address} onChange={(e) => setAddress(e.target.value)} placeholder="ที่อยู่จัดส่ง (เลขที่ ซอย ถนน แขวง เขต จังหวัด)" />
        <input className="hdr-pop-input" style={{ width: 110 }} value={postcode} onChange={(e) => setPostcode(e.target.value)} placeholder="รหัส ปณ." inputMode="numeric" maxLength={5} />
        <button className="btn dark sm" type="submit" disabled={busy === "quote" || postcode.trim().length !== 5}>{busy === "quote" ? "กำลังคำนวณ…" : "คำนวณค่าส่ง"}</button>
      </form>
      {!needsShip && <div className="note small" style={{ marginTop: 8 }}>ทุกรายการยกกลับจากสาขา — ไม่มีค่าจัดส่ง</div>}
      {err && <div className="note err small" style={{ marginTop: 8 }}>{err}</div>}

      {quote && (
        <>
          <div className="col" style={{ marginTop: 12 }}>
            {quote.groups.map((g) => (
              <div key={g.mode} className="group-box">
                <Icon name={g.mode === "takeaway" ? "shopping_bag" : g.mode === "install" ? "handyman" : "local_shipping"} size={22} />
                <div className="grow">
                  <b>{g.label}{g.mode === "takeaway" && g.items[0]?.plant_code ? ` · ${plantName(g.items[0].plant_code)}` : g.mode !== "takeaway" ? " · คลังบางพลี" : ""}</b>
                  <div className="small muted">{g.items.map((it) => `${it.name} ×${it.qty}`).join(" · ")}</div>
                </div>
                <b className={g.fee_note ? "green" : ""}>{g.fee_note || (g.mode === "install" ? `ค่าติดตั้ง ${bahtWord(quote.install_fee)}` : `ค่าส่ง ${bahtWord(quote.base_fee)}`)}</b>
              </div>
            ))}
            <div className="row between small">
              <span><Icon name="place" size={16} /> {address || "ไม่ระบุที่อยู่"} {quote.postcode} · เขตส่ง {quote.zone} ({quote.zone_name})</span>
              <b>รวมค่าส่ง+ติดตั้ง {bahtWord(quote.total_fee)}</b>
            </div>
          </div>

          {needsShip && (
            <div style={{ marginTop: 12 }}>
              <div className="row between" style={{ marginBottom: 6 }}>
                <b className="small">เลือกคิวจัดส่ง</b>
                <span className="small muted">{quote.held_slot_id ? "จองชั่วคราว 15 นาที — ยืนยันเมื่อออกใบเสนอราคา" : "ยังไม่ได้เลือกคิว"}</span>
              </div>
              <div className="slot-grid">
                {[...byDate.entries()].map(([d, slots]) => (
                  slots.map((s) => (
                    <button key={s.id} type="button" className={"slot" + (s.held_by_this_cart ? " on" : "") + (s.remaining <= 0 && !s.held_by_this_cart ? " full" : "")} disabled={busy !== null || (s.remaining <= 0 && !s.held_by_this_cart)} onClick={() => hold(s.id)}>
                      <span>{thDate(d)} {s.period === "am" ? "เช้า" : "บ่าย"}</span>
                      <b className={s.remaining > 0 ? "green" : "red"}>{s.held_by_this_cart ? "จองแล้ว" : s.remaining > 0 ? `คิวว่าง ${s.remaining}` : "คิวเต็ม"}</b>
                    </button>
                  ))
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
