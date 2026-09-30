import { useEffect, useState, type FormEvent } from "react";
import { apiPost, errorMessage } from "../lib/api";
import { useContent } from "../lib/content";
import { bahtWord, thDate } from "../lib/format";
import type { Cart, DeliveryQuote, DeliverySlot } from "../lib/types";
import Icon from "./Icon";
import RemoteAreaCheck from "./RemoteAreaCheck";
import SlotCalendar from "./SlotCalendar";

type Props = {
  cart: Cart;
  defaultPostcode?: string | null;
  defaultAddress?: string | null;
  onChanged: () => Promise<void> | void;
  compact?: boolean;
  /** ลูกค้าไม่ได้เลือกคิวจัดส่งเอง — ทีมจัดส่งจัดคิวให้แล้วโทรยืนยันวันทีหลัง */
  hideSlots?: boolean;
  /** ที่อยู่มาจากสมุดที่อยู่ข้างนอก ไม่ต้องมีช่องกรอกในแผงนี้ (คิดค่าส่งให้อัตโนมัติ) */
  autoQuote?: boolean;
};

/** S4 · ค่าขนส่งตามเขต + แยกกลุ่ม ยกกลับ/ส่ง/ติดตั้ง + จองคิวจัดส่ง (hold 15 นาที) */
export default function DeliveryPanel({ cart, defaultPostcode, defaultAddress, onChanged, compact, hideSlots, autoQuote }: Props) {
  const { plants } = useContent();
  const [postcode, setPostcode] = useState(cart.delivery?.postcode || defaultPostcode || "");
  const [address, setAddress] = useState(cart.delivery?.address || defaultAddress || "");
  const [quote, setQuote] = useState<DeliveryQuote | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [queueReady, setQueueReady] = useState(false);
  const [queueBlock, setQueueBlock] = useState<string | null>(null);
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

  // โหมดอัตโนมัติ (หน้าสั่งซื้อของลูกค้า): เปลี่ยนที่อยู่ในสมุด → คิดค่าส่งใหม่ให้เลย
  // ไม่ต้องให้กดปุ่ม "คำนวณค่าส่ง" เอง เพราะลูกค้าไม่รู้ว่าต้องกด แล้วไปติดตอนกดสั่งซื้อ
  useEffect(() => {
    if (!autoQuote) return;
    const pc = (defaultPostcode || "").trim();
    setPostcode(pc);
    setAddress(defaultAddress || "");
    if (pc.length !== 5) return;
    setBusy("quote");
    setErr(null);
    apiPost<DeliveryQuote>("/delivery/quote", { cart_id: cart.id, postcode: pc, address: defaultAddress || null })
      .then(async (q) => { setQuote(q); await onChanged(); })
      .catch((e2) => setErr(errorMessage(e2)))
      .finally(() => setBusy(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoQuote, defaultPostcode, defaultAddress, cart.id]);

  /** ขอเขตส่ง/คิวรถจากรหัสไปรษณีย์ตัวแทนของจังหวัดที่พนักงานเลือก
   *  แทนที่ฟอร์มกรอกที่อยู่+รหัส ปณ. เดิม ซึ่งพิมพ์ซ้ำกับข้อมูลลูกค้าที่มีอยู่แล้ว */
  const quoteFor = (pc: string) => {
    if (!pc || pc.length !== 5) return;
    setBusy("quote");
    setErr(null);
    apiPost<DeliveryQuote>("/delivery/quote", { cart_id: cart.id, postcode: pc, address: address || defaultAddress || null })
      .then(async (q) => { setQuote(q); setPostcode(pc); await onChanged(); })
      .catch((e2) => setErr(errorMessage(e2)))
      .finally(() => setBusy(null));
  };

  /** คืน true/false ให้ปฏิทินเอาไปบอกผลตรงปุ่มจอง แทนที่จะเงียบแล้วให้ไปหา error ข้างบนเอง */
  const hold = async (slotId: string): Promise<boolean> => {
    setBusy(slotId);
    setErr(null);
    try {
      await apiPost(`/delivery/slots/${slotId}/hold`, { cart_id: cart.id });
      setQuote(await apiPost<DeliveryQuote>("/delivery/quote", { cart_id: cart.id, postcode: postcode.trim(), address: address || null }));
      await onChanged();
      return true;
    } catch (e2) {
      setErr(errorMessage(e2));
      return false;
    } finally {
      setBusy(null);
    }
  };

  const plantName = (code: string | null) => plants.find((p) => p.plant_code === code)?.name || code || "สาขา";

  return (
    <div className={"card flat" + (compact ? " compact" : "")}>
      <div className="row between wrap" style={{ marginBottom: 8 }}>
        {/* ไม่ใส่ไอคอนรถตรงหัวข้อ — ในกล่องข้างล่างมีไอคอนบอกวิธีรับของอยู่แล้ว
            (รถ = จัดส่ง · ถุง = ยกกลับเอง · ประแจ = ติดตั้ง) ซึ่งเป็นตัวที่บอกอะไรจริงๆ
            ใส่ซ้ำสองที่กลายเป็นรถสองคันติดกันเฉยๆ */}
        <b>ค่าขนส่ง{hideSlots ? "" : " + คิวจัดส่ง"}</b>
        {/* รหัสเขตส่งเป็นภาษาภายใน (A/B/C) ไว้ให้เซลล์ตรวจว่าคิดค่าส่งจากโซนไหน
            ลูกค้าเห็นแล้วไม่ได้ใช้ทำอะไร รู้แค่ว่าต้องจ่ายเท่าไรก็พอ */}
        {!autoQuote && cart.delivery?.quoted_at && <span className="small muted">เขต {cart.delivery.zone} · {cart.delivery.zone_name}</span>}
      </div>
      {/* ฝั่งพนักงานไม่มีช่องที่อยู่/รหัส ปณ. แล้ว — เลือกจังหวัดในบล็อกข้างล่างพอ
          ระบบใช้รหัสไปรษณีย์ตัวแทนของจังหวัดนั้นไปขอเขตส่งกับคิวรถให้เอง
          (ที่อยู่จัดส่งจริงอยู่ในใบเสนอราคา/ข้อมูลลูกค้า ไม่ต้องพิมพ์ซ้ำตรงนี้) */}
      {busy === "quote" && <div className="small muted">กำลังคำนวณคิวจัดส่ง…</div>}
      {!needsShip && <div className="note small" style={{ marginTop: 8 }}>ทุกรายการยกกลับจากสาขา — ไม่มีค่าจัดส่ง</div>}
      {err && <div className="note err small" style={{ marginTop: 8 }}>{err}</div>}

      {/* ฝั่งลูกค้า: อ่านเป็นบรรทัดสั้นๆ หัวข้อบน ค่าล่าง — ที่อยู่ไม่ต้องซ้ำ (อยู่ในการ์ดข้างบนแล้ว)
          รหัสเขต/กฎที่ใช้คิดก็ไม่ต้อง เหลือแค่ "ส่งจากไหน ของอะไรบ้าง ค่าส่งเท่าไร" */}
      {quote && autoQuote && (
        <div className="ship-brief">
          {quote.groups.map((g) => (
            <div key={g.mode} className="ship-brief-row">
              <span className="ship-brief-lbl">
                <Icon name={g.mode === "takeaway" ? "shopping_bag" : g.mode === "install" ? "handyman" : "local_shipping"} size={16} />
                {g.label}{g.mode === "takeaway" && g.items[0]?.plant_code ? ` · ${plantName(g.items[0].plant_code)}` : ""}
              </span>
              {g.items.map((it) => (
                <div key={it.name + it.qty} className="ship-brief-item">{it.name} × {it.qty}</div>
              ))}
            </div>
          ))}
          <div className="ship-brief-row total">
            <span className="ship-brief-lbl">ค่าจัดส่ง{Number(quote.install_fee) > 0 ? " + ติดตั้ง" : ""}</span>
            <b>{quote.ship_needs_review ? "รอเจ้าหน้าที่ประเมิน" : bahtWord(quote.total_fee)}</b>
          </div>
          {quote.ship_needs_review && (
            <div className="note warn small">
              <Icon name="warning" size={16} /> ค่าส่งรายการนี้ยังคิดอัตโนมัติไม่ได้ — เจ้าหน้าที่จะแจ้งราคาก่อนยืนยันคำสั่งซื้อ
            </div>
          )}
        </div>
      )}

      {/* บล็อกคิวจัดส่งฝั่งพนักงาน — ไม่รอ quote แล้ว เพราะ quote เกิดจากการเลือกจังหวัดในบล็อกนี้เอง
          (เดิมต้องกรอกที่อยู่+รหัส ปณ. แล้วกด "คำนวณค่าส่ง" ก่อน บล็อกนี้ถึงจะโผล่) */}
      {!autoQuote && needsShip && !hideSlots && (
        <div style={{ marginTop: 12 }}>
          <RemoteAreaCheck
            cartId={cart.id} rev={cart.updated_at} onAdded={onChanged}
            onReady={setQueueReady} onPostcode={quoteFor} onBlocked={setQueueBlock}
          />
          {/* ปฏิทินเปิดหลังคำนวณค่าจัดส่งเสร็จ — จองวันก่อนแล้วค่อยรู้ว่าค่าส่งเพิ่มอีกสามพัน
              คือการโทรแจ้งลูกค้าใหม่ ซึ่งเสียเครดิตกว่าการรอคำนวณสิบวินาที */}
          <div style={{ marginTop: 10 }}>
            <div className="qcheck-head" style={{ marginBottom: 6 }}>
              <span className={"promo-step-no" + (queueReady && quote ? " on" : "")}>3</span>
              <b>เลือกวันจัดส่ง</b>
              <span className="small muted" style={{ marginLeft: "auto" }}>
                {quote?.held_slot_id ? "จองชั่วคราว 15 นาที — ยืนยันเมื่อออกใบเสนอราคา" : "ยังไม่ได้เลือกคิว"}
              </span>
            </div>
            {queueReady && quote ? (
              <SlotCalendar slots={quote.slots} heldId={quote.held_slot_id} busy={busy !== null} onPick={hold} />
            ) : (
              <div className="note small">
                <Icon name="lock" size={16} /> {queueBlock || (busy === "quote" ? "กำลังดึงคิวของเขตนี้…" : "กำลังเตรียมคิวจัดส่ง…")}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
