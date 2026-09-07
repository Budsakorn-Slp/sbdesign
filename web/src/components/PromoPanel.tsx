import { useCallback, useEffect, useState } from "react";
import { api, apiPost, errorMessage } from "../lib/api";
import { bahtWord } from "../lib/format";
import type { Cart, EvaluateOut } from "../lib/types";
import Icon from "./Icon";

type Props = {
  cart: Cart;
  isStaff: boolean;
  onClose: () => void;
  onCartChange: (c: Cart) => void;
};

/** S3 · เช็คโปรโมชั่น / ส่วนลด / เงื่อนไข — ใช้ทั้งฝั่งเซลล์ (มีส่วนลดพนักงาน) และลูกค้า */
export default function PromoPanel({ cart, isStaff, onClose, onCartChange }: Props) {
  const [data, setData] = useState<EvaluateOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [customPct, setCustomPct] = useState("");
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    try {
      setData(await apiPost<EvaluateOut>("/promotions/evaluate", { cart_id: cart.id }));
      setErr(null);
    } catch (e) {
      setErr(errorMessage(e));
    }
  }, [cart.id]);

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
  const staffPct = (pct: number, why?: string) => run("staff", () => apiPost<Cart>(`/cart/${cart.id}/discounts`, { kind: "staff_manual", percent: pct, reason: why || null }));

  const quota = data?.staff_discount_quota_percent ?? 3;
  const curPct = data?.staff_discount?.percent ? Number(data.staff_discount.percent) : 0;
  const t = data?.totals;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>โปรโมชั่นที่ใช้ได้{data?.customer_name ? ` · ${data.customer_name} (${data.customer_tier || "ทั่วไป"})` : " · ยังไม่ผูกลูกค้า"}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="ปิด"><Icon name="close" /></button>
        </div>
        {data && <div className="small muted" style={{ marginBottom: 10 }}>{data.eligible.length} รายการเข้าเงื่อนไข · {data.ineligible.length} รายการยังไม่เข้า</div>}
        {err && <div className="note err" style={{ marginBottom: 10 }}>{err}</div>}
        {!data && !err && <div className="ph" style={{ height: 120 }}>กำลังประเมินโปรโมชั่น…</div>}

        {data && (
          <div className="promo-list">
            {data.eligible.map((o) => (
              <div key={o.code} className={"promo-row" + (o.applied ? " on" : "")}>
                <Icon name={o.applied ? "check_circle" : o.discount_type === "gift" ? "card_giftcard" : "local_offer"} size={22} style={{ color: "var(--green)" }} />
                <div className="grow">
                  <b>{o.code} · {o.title}</b>
                  <small>เงื่อนไข: {o.condition_text}{o.stackable ? "" : " · ใช้ร่วมกับโปรอื่นไม่ได้"}</small>
                  <small className="green">{o.applied ? "ใช้กับบิลนี้แล้ว" : "เข้าเงื่อนไข กดใช้ได้เลย"}</small>
                </div>
                <div className="col" style={{ alignItems: "flex-end" }}>
                  <b className="green">−{bahtWord(o.amount)}</b>
                  {o.applied && o.applied_id ? (
                    <button className="btn green sm" disabled={busy === o.applied_id} onClick={() => removeDiscount(o.applied_id!)}>ยกเลิก</button>
                  ) : (
                    <button className="btn sm" disabled={busy === o.code} onClick={() => applyPromo(o.code)}>กดใช้</button>
                  )}
                </div>
              </div>
            ))}
            {data.ineligible.map((o) => (
              <div key={o.code} className="promo-row no">
                <Icon name="error" size={22} style={{ color: "var(--amber)" }} />
                <div className="grow">
                  <b>{o.code} · {o.title}</b>
                  <small>เงื่อนไข: {o.condition_text}</small>
                  <small className="amber">{o.reason}</small>
                </div>
                <div className="col" style={{ alignItems: "flex-end" }}>
                  <b className="muted">—</b>
                  <button className="btn sm" disabled title={o.reason || ""}>ดูเงื่อนไข</button>
                </div>
              </div>
            ))}
          </div>
        )}

        {isStaff && data && (
          <div className="card flat" style={{ marginTop: 14 }}>
            <div className="row between wrap">
              <div><b>ส่วนลดพนักงาน (manual)</b> <span className="small muted">โควตา {quota}% · เกินต้องขออนุมัติผู้จัดการสาขาในแอป</span></div>
              {data.staff_discount && <span className={"chip " + (data.staff_discount.status === "applied" ? "green" : "amber")}>{data.staff_discount.status === "applied" ? "ใช้แล้ว" : "รออนุมัติ"} {Number(data.staff_discount.percent)}% · −{bahtWord(data.staff_discount.amount)}</span>}
            </div>
            <div className="row wrap" style={{ marginTop: 10, gap: 10 }}>
              <div className="disc-steps">
                {[0, 1, 2, 3].map((v) => (
                  <button key={v} className={curPct === v && (data.staff_discount?.status === "applied" || v === 0) ? "on" : ""} disabled={busy === "staff"} onClick={() => staffPct(v)}>{v === 0 ? "ไม่ใช้" : `${v}%`}</button>
                ))}
              </div>
              <form className="row" onSubmit={(e) => { e.preventDefault(); const p = parseFloat(customPct); if (!Number.isNaN(p)) staffPct(p, reason); }}>
                <input className="hdr-pop-input" style={{ width: 70 }} value={customPct} onChange={(e) => setCustomPct(e.target.value)} placeholder="%" inputMode="decimal" />
                <input className="hdr-pop-input" style={{ width: 200 }} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="เหตุผล (กรณีเกินโควตา)" />
                <button className="btn dark sm" type="submit" disabled={busy === "staff" || !customPct}>{parseFloat(customPct) > quota ? "ขออนุมัติ" : "ใส่ส่วนลด"}</button>
              </form>
            </div>
          </div>
        )}

        {t && (
          <div className="summary" style={{ marginTop: 14 }}>
            <h3>สรุปหลังส่วนลด</h3>
            <div className="sum-row"><span>ราคาปกติ</span><span>{bahtWord(t.standard_subtotal)}</span></div>
            {Number(t.member_savings) > 0 && <div className="sum-row"><span>ราคาสมาชิก</span><span className="green">−{bahtWord(t.member_savings)}</span></div>}
            {t.lines.map((l) => (
              <div key={l.id} className="sum-row">
                <span>{l.title}{l.status === "pending_approval" ? " (รออนุมัติ)" : ""}</span>
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
