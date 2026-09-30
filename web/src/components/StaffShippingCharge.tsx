import { useEffect, useState } from "react";
import Icon from "./Icon";
import { apiDelete, apiGet, apiPost, errorMessage } from "../lib/api";

/** ค่าขนส่งฝั่งพนักงาน — "เปิด Mat" ค่าขนส่งเป็นบรรทัดสินค้าจริงในบิล (A534 / A761)
 *
 *  คนละเรื่องกับค่าส่งหน้าเว็บลูกค้า ซึ่งคิดจากรหัสไปรษณีย์/น้ำหนักตามกฎ Amasty
 *  ฝั่งนี้ดูยอดบิลอย่างเดียว แล้วเปิดรหัสค่าบริการตามเทียร์ที่ทีมขายตกลงกันไว้
 *
 *  ตัวเลขที่ระบบเสนอแก้ทับได้เสมอ เพราะหน้าสาขาเจอเคสนอกกฎประจำ (ของชิ้นใหญ่
 *  ต่างจังหวัดไกล ลูกค้าต่อรอง) — แต่ทุกครั้งที่แก้จะถูกบันทึกว่าใครแก้ พร้อมหมายเหตุ
 */
type Suggest = {
  goods_subtotal: string;
  matnr: string;
  name: string;
  fee: string;
  tier_label: string;
  current: null | { item_id: string; matnr: string; name: string; fee: string; remark: string | null; matches_rule: boolean };
};

const baht = (v: string | number) => Number(v).toLocaleString("th-TH", { minimumFractionDigits: 0, maximumFractionDigits: 2 });

export default function StaffShippingCharge({ cartId, rev, onChanged }: { cartId: string; rev?: string | number; onChanged: () => void }) {
  const [s, setS] = useState<Suggest | null>(null);
  const [matnr, setMatnr] = useState("");
  const [fee, setFee] = useState("");
  const [remark, setRemark] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const load = async () => {
    const r = await apiGet<Suggest>(`/sales/carts/${cartId}/shipping-charge`);
    setS(r);
    // ยังไม่เคยเปิด Mat = ตั้งค่าตามที่กฎเสนอ · เปิดไว้แล้ว = โชว์ของจริงที่อยู่ในบิล
    setMatnr(r.current?.matnr || r.matnr);
    setFee(r.current?.fee ?? r.fee);
    setRemark(r.current?.remark || "");
  };

  // rev เปลี่ยน = ตะกร้าขยับ (เพิ่ม/ลบของ หรือบล็อกคิวจัดส่งบวกค่าพื้นที่ห่างไกลเข้ามา)
  // ต้องดึงใหม่ ไม่งั้นแถบนี้โชว์ตัวเลขเก่าที่ไม่ตรงกับบิล
  useEffect(() => {
    load().catch((e) => setErr(errorMessage(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cartId, rev]);

  if (!s) return null;

  const ruleFee = s.fee;
  // เทียบเป็นตัวเลข ไม่ใช่ข้อความ — ฝั่งหลังบ้านคืน "600.00" แต่กฎเขียนไว้ "600"
  // ถ้าเทียบเป็นข้อความจะขึ้นเตือน "แก้จากกฎ" ทั้งที่พนักงานใช้ตามกฎเป๊ะ
  const edited = Number(fee) !== Number(ruleFee) || matnr !== s.matnr;
  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      await apiPost(`/sales/carts/${cartId}/shipping-charge`, { matnr, fee, remark: remark.trim() || null });
      await load();
      onChanged();
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const clear = async () => {
    setBusy(true);
    setErr(null);
    try {
      await apiDelete(`/sales/carts/${cartId}/shipping-charge`);
      await load();
      onChanged();
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="ship-charge">
      <button type="button" className="ship-charge-head" onClick={() => setOpen((v) => !v)}>
        <Icon name="local_shipping" size={18} />
        <b>ค่าขนส่ง (เปิด Mat)</b>
        {s.current ? (
          <span className="ship-charge-now">
            {s.current.matnr} · {baht(s.current.fee)} บาท
          </span>
        ) : (
          <span className="ship-charge-now muted">ยังไม่ได้เปิด — กฎเสนอ {s.matnr} · {baht(ruleFee)} บาท</span>
        )}
        <Icon name={open ? "expand_less" : "expand_more"} size={18} />
      </button>

      {open && (
        <div className="ship-charge-body">
          <div className="tiny muted">
            ยอดสินค้าที่ติ๊กไว้ {baht(s.goods_subtotal)} บาท → เข้าเทียร์ <b>{s.tier_label}</b> · กฎเสนอ {s.matnr} = {baht(ruleFee)} บาท
          </div>

          <div className="ship-charge-grid">
            <label className="field">
              <span>รหัสค่าบริการ</span>
              <select value={matnr} onChange={(e) => setMatnr(e.target.value)}>
                <option value="A534">A534 · ค่าบริการขนส่งคำสั่งซื้อขนาดเล็ก</option>
                <option value="A761">A761 · ค่าขนส่งพิเศษ-ออฟไลน์</option>
              </select>
            </label>
            <label className="field">
              <span>ค่าขนส่ง (บาท)</span>
              <input value={fee} onChange={(e) => setFee(e.target.value)} inputMode="decimal" />
            </label>
            <label className="field span2">
              <span>หมายเหตุ</span>
              <input value={remark} onChange={(e) => setRemark(e.target.value)} placeholder="เช่น ของชิ้นใหญ่ ส่งต่างจังหวัด · ตกลงกับลูกค้าแล้ว" />
            </label>
          </div>

          {err && <div className="note err tiny">{err}</div>}

          <div className="row" style={{ gap: 8 }}>
            <button className="btn dark sm" disabled={busy} onClick={save}>
              {busy ? "กำลังบันทึก…" : s.current ? "อัปเดตค่าขนส่ง" : "เปิด Mat เข้าบิล"}
            </button>
            {edited && (
              <button className="btn sm" disabled={busy} onClick={() => { setMatnr(s.matnr); setFee(ruleFee); }}>
                ใช้ตามกฎ
              </button>
            )}
            {s.current && (
              <button className="link-btn small danger" disabled={busy} onClick={clear}>
                เอาออกจากบิล
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
