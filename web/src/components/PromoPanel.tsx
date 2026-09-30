import { useCallback, useEffect, useState } from "react";
import { ApiError, api, apiGet, apiPost, errorMessage } from "../lib/api";
import { bahtWord } from "../lib/format";
import type { Cart, EvaluateOut, Offer } from "../lib/types";
import Icon from "./Icon";

type Props = {
  cart: Cart;
  /** ใครเปิดแผงนี้ · คนละสิทธิ์กันคนละโหมด
   *    staff     พนักงานถือตะกร้า — เช็คโปรฯ เป็นขั้น ติ๊กเลือก กรอกโค้ด ครบทุกอย่าง
   *    customer  ลูกค้าสั่งออนไลน์เอง — กรอกโค้ดได้อย่างเดียว ไม่มีแผงเช็คโปรฯ
   *    readonly  ลูกค้าที่พนักงานกำลังดูแล — ดูส่วนลดที่ได้รับ แก้อะไรไม่ได้
   */
  mode?: "staff" | "customer" | "readonly";
  /** @deprecated ใช้ mode แทน — เหลือไว้ให้หน้าเก่าที่ยังส่งมาไม่พัง */
  isStaff?: boolean;
  onClose: () => void;
  onCartChange: (c: Cart) => void;
};

/** S3 · เช็คโปรโมชั่น / โปรโมโค้ด / ส่วนลดพนักงาน — ใช้ทั้งฝั่งเซลล์และลูกค้า
 *
 *  โฟลว์เป็น 2 ขั้นในหน้าเดียว ตามที่หน้าร้านใช้จริง:
 *    ขั้น 1  เช็คโปรโมชั่น  — ระบบไล่ดู MATNR ทุกตัวในตะกร้าให้เอง แล้วติ๊กเลือกใช้
 *    ขั้น 2  โปรโมโค้ด     — เปิดให้ใช้ "หลังเช็คขั้น 1 แล้ว" เลือกจากคูปองที่มี หรือพิมพ์โค้ดเอง
 *
 *  ทำไมต้องล็อกขั้น 2 ไว้ก่อน: ส่วนลดหลายตัวชนกัน (ตัวที่ stackable=false ใช้ร่วมกับใครไม่ได้)
 *  ถ้าปล่อยให้กรอกโค้ดตั้งแต่ยังไม่รู้ว่าโปรฯ อัตโนมัติให้อะไรบ้าง พนักงานจะเลือกทางที่แย่กว่า
 *  โดยไม่รู้ตัว — เช็คก่อนแล้วค่อยเติมโค้ด ทำให้เห็นครบว่าอันไหนคุ้มกว่า
 */
export default function PromoPanel({ cart, mode, isStaff, onClose, onCartChange }: Props) {
  const view = mode ?? (isStaff ? "staff" : "customer");
  const staff = view === "staff";
  const staffMode = staff;
  const readonly = view === "readonly";
  const [data, setData] = useState<EvaluateOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);   // ขั้น 1 เช็คไปแล้วอย่างน้อย 1 รอบ
  const [codeInput, setCodeInput] = useState("");

  const load = useCallback(async () => {
    try {
      setData(await apiPost<EvaluateOut>("/promotions/evaluate", { cart_id: cart.id }));
      setChecked(true);
      setErr(null);
    } catch (e) {
      // ตะกร้าใบที่หน้าจอถืออยู่ใช้ไม่ได้แล้ว — เกิดตอนพนักงานปลดลูกค้าออกจากใบนั้น
      // หรือใบถูกปิด/หมดอายุ ระหว่างที่ลูกค้าเปิดหน้าค้างไว้
      //
      // ของเดิมโชว์ "ไม่มีสิทธิ์เข้าถึงตะกร้านี้" ให้ลูกค้าอ่าน ซึ่งไม่ได้ช่วยอะไร
      // และไม่ใช่ความผิดลูกค้าด้วย — ดึงใบปัจจุบันมาใช้แทนแล้วลองใหม่เงียบๆ
      const stale = e instanceof ApiError && (e.status === 403 || e.status === 404);
      if (stale && !staffMode) {
        try {
          const fresh = await apiGet<Cart>("/cart");
          if (fresh.id !== cart.id) {
            onCartChange(fresh);
            setData(await apiPost<EvaluateOut>("/promotions/evaluate", { cart_id: fresh.id }));
            setChecked(true);
            setErr(null);
            return;
          }
        } catch {
          /* ดึงใบใหม่ไม่ได้ ตกไปแสดง error เดิม */
        }
      }
      setErr(errorMessage(e));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cart.id]);

  // เช็คให้เลยตั้งแต่เปิดหน้า ไม่ต้องให้กดปุ่มก่อน — ข้อมูลที่ใช้เช็คคือของในตะกร้าซึ่งมีอยู่แล้ว
  useEffect(() => {
    load();
  }, [load, cart.updated_at]);

  const run = async (key: string, fn: () => Promise<Cart>) => {
    setBusy(key);
    setErr(null);
    try {
      onCartChange(await fn());
      await load();
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const applyPromo = (code: string) => run(code, () => apiPost<Cart>(`/cart/${cart.id}/discounts`, { kind: "promotion", promo_code: code }));
  const removeDiscount = (id: string) => run(id, () => api<Cart>("DELETE", `/cart/${cart.id}/discounts/${id}`));

  const t = data?.totals;

  // ฝั่งหลังบ้านคัดคูปองที่ต้องใช้โค้ดออกให้แล้ว ลิสต์นี้จึงมีแต่โปรฯ ที่ระบบเช็คเอง
  const autos: Offer[] = [...(data?.eligible ?? []), ...(data?.ineligible ?? [])];
  const autoOk = autos.filter((o) => o.eligible).length;

  /** หนึ่งบรรทัด = หนึ่งสิทธิ์ · ติ๊กเพื่อใช้ ติ๊กออกเพื่อยกเลิก (ของที่ยังไม่เข้าเงื่อนไขติ๊กไม่ได้) */
  const OfferRow = ({ o }: { o: Offer }) => {
    const key = o.applied ? o.applied_id! : o.code;
    const toggle = () => (o.applied && o.applied_id ? removeDiscount(o.applied_id) : applyPromo(o.code));
    return (
      <label className={"promo-row" + (o.applied ? " on" : o.eligible ? "" : " no")}>
        <input
          type="checkbox"
          className="promo-tick"
          checked={o.applied}
          disabled={!o.eligible || busy === key}
          onChange={toggle}
        />
        <div className="grow">
          <b>{o.code} · {o.title}</b>
          <small>เงื่อนไข: {o.condition_text}{o.stackable ? "" : " · ใช้ร่วมกับโปรอื่นไม่ได้"}</small>
          {o.eligible
            ? <small className="green">{o.applied ? "ใช้กับบิลนี้แล้ว" : "เข้าเงื่อนไข ติ๊กเพื่อใช้"}</small>
            : <small className="amber">{o.reason}</small>}
        </div>
        <b className={o.eligible ? "green" : "muted"}>{o.eligible ? `−${bahtWord(o.amount)}` : "—"}</b>
      </label>
    );
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{readonly ? "ส่วนลดที่ได้รับ" : staff ? `ส่วนลดของบิลนี้${data?.customer_name ? ` · ${data.customer_name}` : " · ยังไม่ผูกลูกค้า"}` : "โค้ดส่วนลด"}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="ปิด"><Icon name="close" /></button>
        </div>

        {err && <div className="note err" style={{ marginBottom: 10 }}>{err}</div>}
        {!data && !err && <div className="ph" style={{ height: 120 }}>กำลังเช็คโปรโมชั่นจากสินค้าในตะกร้า…</div>}

        {data && (
          <>
            {/* ---------- ขั้น 1 · โปรโมชั่นอัตโนมัติ (พนักงานเท่านั้น) ----------
                ลูกค้าไม่เห็นขั้นนี้ เพราะโปรฯ หน้าร้านต้องมีพนักงานเป็นคนตรวจและกดให้
                ฝั่งออนไลน์ลูกค้ามีทางเดียวคือกรอกโค้ด เหมือนร้านค้าออนไลน์ทั่วไป */}
            {staff && (
              <div className="promo-step">
                <div className="promo-step-head">
                  <span className="promo-step-no on">1</span>
                  <div className="grow">
                    <b>Promotion</b>
                    <small className="muted">เช็คจากรหัสสินค้าทุกตัวให้แล้ว · เข้าเงื่อนไข {autoOk} จาก {autos.length} รายการ</small>
                  </div>
                  <button className="btn sm" disabled={!!busy} onClick={load}>เช็คใหม่</button>
                </div>
                <div className="promo-list">
                  {autos.length ? autos.map((o) => <OfferRow key={o.code} o={o} />)
                    : <div className="small muted" style={{ padding: "8px 2px" }}>ไม่มีโปรโมชั่นที่ตรงกับสินค้าในตะกร้านี้</div>}
                </div>
              </div>
            )}

            {/* ---------- ขั้น 2 · โปรโมโค้ด ----------
                พนักงาน: ปลดล็อกหลังเช็คขั้น 1 · ลูกค้าออนไลน์: ใช้ได้เลย ไม่มีขั้นก่อนหน้า
                ลูกค้าที่พนักงานดูแลอยู่: ไม่เห็นช่องนี้ ส่วนลดเป็นหน้าที่ของพนักงาน */}
            {!readonly && (
              <div className={"promo-step" + (checked || !staff ? "" : " locked")}>
                <div className="promo-step-head">
                  {staff && <span className={"promo-step-no" + (checked ? " on" : "")}>2</span>}
                  <div className="grow">
                    <b>PromoCode</b>
                    <small className="muted">
                      {staff && !checked ? "เช็ค Promotion ขั้นที่ 1 ให้เสร็จก่อน" : "กรอกรหัสโปรโมโค้ดที่มี"}
                    </small>
                  </div>
                </div>
                {(checked || !staff) && (
                  <form
                    className="promo-code-form"
                    onSubmit={(e) => { e.preventDefault(); const c = codeInput.trim().toUpperCase(); if (c) { applyPromo(c); setCodeInput(""); } }}
                  >
                    <Icon name="confirmation_number" size={18} />
                    <input
                      value={codeInput}
                      onChange={(e) => setCodeInput(e.target.value.toUpperCase())}
                      placeholder={staff ? "มีโค้ดจากลูกค้า? พิมพ์ที่นี่" : "กรอกโค้ดส่วนลด"}
                      autoComplete="off"
                    />
                    <button className="btn dark sm" type="submit" disabled={!codeInput.trim() || !!busy}>ใช้โค้ด</button>
                  </form>
                )}
              </div>
            )}

            {readonly && (
              <div className="note small">
                พนักงานกำลังดูแลตะกร้านี้อยู่ ส่วนลดด้านล่างเป็นสิทธิ์ที่พนักงานใส่ให้
                {t && !t.lines.length ? " — ตอนนี้ยังไม่มีส่วนลด" : ""}
                <div className="tiny muted" style={{ marginTop: 4 }}>อยากใส่โค้ดเอง ให้กด "ออกจากการดูแล" ที่หน้าตะกร้าก่อน</div>
              </div>
            )}
          </>
        )}

        {t && (
          <div className="summary" style={{ marginTop: 14 }}>
            <h3>สรุปหลังส่วนลด</h3>
            <div className="sum-row"><span>ราคาปกติ</span><span>{bahtWord(t.standard_subtotal)}</span></div>
            {Number(t.member_savings) > 0 && <div className="sum-row"><span>ราคาสมาชิก</span><span className="green">−{bahtWord(t.member_savings)}</span></div>}
            {/* ทุกบรรทัดต้องถอดออกได้จากตรงนี้ — โค้ดที่กรอกผิดไม่มีลิสต์ให้กลับไปติ๊กออกแล้ว */}
            {t.lines.filter((l) => Number(l.amount) > 0).map((l) => (
              <div key={l.id} className="sum-row">
                <span>
                  {l.title}{l.status === "pending_approval" ? " (รออนุมัติ)" : ""}
                  {!readonly && <button className="link-btn small danger" style={{ marginLeft: 8 }} disabled={busy === l.id} onClick={() => removeDiscount(l.id)}>เอาออก</button>}
                </span>
                <span className={l.status === "applied" ? "green" : "muted"}>−{bahtWord(l.amount)}</span>
              </div>
            ))}
            {t.warnings.map((w) => (
              <div key={w} className="note warn small" style={{ marginTop: 6 }}>{w}</div>
            ))}
            <div className="sum-total"><span>ยอดสินค้า</span><b>{bahtWord(t.net_total)}</b></div>
          </div>
        )}
      </div>
    </div>
  );
}
