import { useEffect, useState } from "react";
import Icon from "./Icon";
import { apiDelete, apiGet, apiPost, errorMessage } from "../lib/api";

/** ค่าขนส่งฝั่งพนักงาน — "เปิด Mat" ค่าขนส่งเป็นบรรทัดสินค้าจริงในบิล (A534 / A761 / A776)
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
  // รหัสที่เลือกได้ มาจากไฟล์กฎฝั่งหลังบ้าน ไม่ได้ฮาร์ดโค้ดไว้ตรงนี้
  // เพิ่มรหัสใหม่ในไฟล์กฎแล้วช่องเลือกขึ้นเอง ไม่ต้องแก้หน้าเว็บ
  options: ChargeOption[];
  // หนึ่งบล็อกต่อหนึ่งบทบาท (ตามยอดบิล / เหมา / ค่าแพ็ค) — ต่างบทบาทบวกกันได้
  roles: RoleBlock[];
  current: null | { item_id: string; matnr: string; name: string; fee: string; remark: string | null; matches_rule: boolean };
};

type ChargeOption = { matnr: string; name: string; default_fee: string | null };

type RoleBlock = {
  role: string;
  label: string;
  hint: string | null;
  options: ChargeOption[];
  default_matnr: string | null;
  default_fee: string | null;
  current: null | { item_id: string; matnr: string; name: string; fee: string; remark: string | null };
};

/** ค่าที่กรอกอยู่ในบล็อกหนึ่ง — เก็บแยกตาม role เพราะเปิดพร้อมกันได้หลายบรรทัด */
type Draft = { matnr: string; fee: string; remark: string };

const baht = (v: string | number) => Number(v).toLocaleString("th-TH", { minimumFractionDigits: 0, maximumFractionDigits: 2 });

export default function StaffShippingCharge({ cartId, rev, onChanged }: { cartId: string; rev?: string | number; onChanged: () => void }) {
  const [s, setS] = useState<Suggest | null>(null);
  const [draft, setDraft] = useState<Record<string, Draft>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const load = async () => {
    const r = await apiGet<Suggest>(`/sales/carts/${cartId}/shipping-charge`);
    setS(r);
    // ยังไม่เคยเปิด Mat = ตั้งค่าตามที่กฎเสนอ · เปิดไว้แล้ว = โชว์ของจริงที่อยู่ในบิล
    // role tier มีเทียร์เป็นตัวเสนอ · role อื่นใช้ default_fee ของรหัสตัวแรก
    const d: Record<string, Draft> = {};
    for (const b of r.roles || []) {
      const ruled = b.role === "tier" ? { matnr: r.matnr, fee: r.fee } : { matnr: b.default_matnr || "", fee: b.default_fee || "" };
      d[b.role] = {
        matnr: b.current?.matnr || ruled.matnr,
        fee: b.current?.fee ?? ruled.fee,
        remark: b.current?.remark || "",
      };
    }
    setDraft(d);
  };

  // rev เปลี่ยน = ตะกร้าขยับ (เพิ่ม/ลบของ หรือบล็อกคิวจัดส่งบวกค่าพื้นที่ห่างไกลเข้ามา)
  // ต้องดึงใหม่ ไม่งั้นแถบนี้โชว์ตัวเลขเก่าที่ไม่ตรงกับบิล
  useEffect(() => {
    load().catch((e) => setErr(errorMessage(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cartId, rev]);

  if (!s) return null;

  const ruleFee = s.fee;
  const blocks = s.roles || [];
  const opened = blocks.filter((b) => b.current);
  const set = (role: string, patch: Partial<Draft>) =>
    setDraft((d) => ({ ...d, [role]: { ...d[role], ...patch } }));

  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    setErr(null);
    try {
      await fn();
      await load();
      onChanged();
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };
  const save = (role: string) => {
    const d = draft[role];
    if (!d?.matnr) return;
    return run(role, () =>
      apiPost(`/sales/carts/${cartId}/shipping-charge`, { matnr: d.matnr, fee: d.fee, remark: d.remark.trim() || null }));
  };
  const clear = (role: string) =>
    run(role, () => apiDelete(`/sales/carts/${cartId}/shipping-charge?role=${role}`));

  return (
    <div className="ship-charge">
      <button type="button" className="ship-charge-head" onClick={() => setOpen((v) => !v)}>
        <Icon name="local_shipping" size={18} />
        <b>ค่าขนส่ง (เปิด Mat)</b>
        {opened.length ? (
          <span className="ship-charge-now">
            {opened.map((b) => `${b.current!.matnr} · ${baht(b.current!.fee)}`).join("  +  ")} บาท
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

          {err && <div className="note err tiny">{err}</div>}

          {/* หนึ่งบล็อกต่อหนึ่งบทบาท — ต่างบทบาทเปิดพร้อมกันได้ เช่น ตัวโชว์ส่งต่างจังหวัด
              จะมีทั้งค่าเหมา ค่าตามยอดบิล และค่าพื้นที่ห่างไกล คนละบรรทัดในบิลเดียว */}
          {blocks.map((b) => {
            const d = draft[b.role] || { matnr: "", fee: "", remark: "" };
            const ruled = b.role === "tier" ? { matnr: s.matnr, fee: ruleFee } : { matnr: b.default_matnr || "", fee: b.default_fee || "" };
            // เทียบเป็นตัวเลข ไม่ใช่ข้อความ — หลังบ้านคืน "600.00" แต่กฎเขียนไว้ "600"
            const edited = !!ruled.matnr && (Number(d.fee) !== Number(ruled.fee) || d.matnr !== ruled.matnr);
            const mine = busy === b.role;
            return (
              <div key={b.role} className={`charge-block${b.current ? " on" : ""}`}>
                <div className="charge-block-head">
                  <b>{b.label}</b>
                  {b.current
                    ? <span className="chip green">เปิดแล้ว · {baht(b.current.fee)} บาท</span>
                    : <span className="chip light">ยังไม่ได้เปิด</span>}
                </div>
                {b.hint && <div className="tiny muted">{b.hint}</div>}

                <div className="ship-charge-grid">
                  <label className="field">
                    <span>รหัสค่าบริการ</span>
                    <select value={d.matnr} onChange={(e) => {
                      // เปลี่ยนรหัสแล้วเติมราคาตั้งต้นของรหัสนั้นให้ ถ้ายังไม่เคยเปิดบรรทัดนี้
                      const o = b.options.find((x) => x.matnr === e.target.value);
                      set(b.role, { matnr: e.target.value, ...(!b.current && o?.default_fee ? { fee: o.default_fee } : {}) });
                    }}>
                      {b.options.map((o) => (
                        <option key={o.matnr} value={o.matnr}>{o.matnr} · {o.name}</option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>จำนวนเงิน (บาท)</span>
                    <input value={d.fee} onChange={(e) => set(b.role, { fee: e.target.value })} inputMode="decimal" />
                  </label>
                  <label className="field span2">
                    <span>หมายเหตุ</span>
                    <input value={d.remark} onChange={(e) => set(b.role, { remark: e.target.value })}
                           placeholder="เช่น ของชิ้นใหญ่ ส่งต่างจังหวัด · ตกลงกับลูกค้าแล้ว" />
                  </label>
                </div>

                <div className="row" style={{ gap: 8 }}>
                  <button className="btn dark sm" disabled={!!busy || !d.matnr} onClick={() => save(b.role)}>
                    {mine ? "กำลังบันทึก…" : b.current ? "อัปเดต" : "เปิด Mat เข้าบิล"}
                  </button>
                  {edited && (
                    <button className="btn sm" disabled={!!busy} onClick={() => set(b.role, { matnr: ruled.matnr, fee: ruled.fee })}>
                      ใช้ตามกฎ
                    </button>
                  )}
                  {b.current && (
                    <button className="link-btn small danger" disabled={!!busy} onClick={() => clear(b.role)}>
                      เอาออกจากบิล
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
