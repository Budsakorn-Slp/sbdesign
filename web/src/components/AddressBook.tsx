import { useEffect, useState } from "react";
import AddressPicker from "./AddressPicker";
import Icon from "./Icon";
import { apiDelete, apiGet, apiPatch, apiPost, errorMessage } from "../lib/api";
import type { SavedAddress } from "../lib/types";

/** สมุดที่อยู่จัดส่ง — เก็บได้หลายที่อยู่ เลือกตอนสั่งซื้อ (บ้าน/ที่ทำงาน/ส่งให้คนอื่น)
 *
 *  ที่อยู่นี้ใช้ส่งของอย่างเดียว เปลี่ยนได้ตลอดจนกว่าจะยืนยันคำสั่งซื้อ และค่าส่งจะคิดใหม่
 *  ทุกครั้งที่เปลี่ยน เพราะค่าส่งผูกกับรหัสไปรษณีย์ปลายทาง
 */
type Draft = {
  label: string; receiver: string; phone: string; address: string;
  sub: string; district: string; province: string; postcode: string; note: string; is_default: boolean;
};

const EMPTY: Draft = { label: "", receiver: "", phone: "", address: "", sub: "", district: "", province: "", postcode: "", note: "", is_default: false };

export default function AddressBook({
  selectedId, onSelect, defaults, manage,
}: {
  selectedId: string | null;
  onSelect: (a: SavedAddress | null) => void;
  /** ค่าตั้งต้นตอนเพิ่มใบแรก — ดึงจากโปรไฟล์/จังหวัดที่เลือกไว้บนหัวเว็บ จะได้ไม่ต้องพิมพ์ซ้ำ */
  defaults?: Partial<Draft>;
  /** โหมดจัดการในหน้าบัญชี: กางรายการทั้งหมดตลอด ปุ่มกลมคือ "ตั้งเป็นค่าเริ่มต้น"
   *  (หน้าสั่งซื้อใช้โหมดปกติ: เห็นใบที่เลือกใบเดียว กด "เปลี่ยน" ถึงจะกาง) */
  manage?: boolean;
}) {
  const [rows, setRows] = useState<SavedAddress[] | null>(null);
  const [open, setOpen] = useState(Boolean(manage));   // กางรายการที่อยู่ทั้งหมด
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = async (pick?: string) => {
    const list = await apiGet<SavedAddress[]>("/me/addresses");
    setRows(list);
    // เลือกให้อัตโนมัติ: ใบที่เพิ่งบันทึก > ใบที่เลือกอยู่ > ใบค่าเริ่มต้น > ใบแรก
    const keep = list.find((a) => a.id === (pick || selectedId));
    onSelect(keep || list.find((a) => a.is_default) || list[0] || null);
    return list;
  };

  useEffect(() => {
    load().catch(() => setRows([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startNew = () => {
    setDraft({ ...EMPTY, ...defaults, is_default: !rows?.length });
    setEditing("new");
    setErr(null);
  };

  const startEdit = (a: SavedAddress) => {
    setDraft({
      label: a.label || "", receiver: a.receiver, phone: a.phone, address: a.address,
      sub: a.sub || "", district: a.district || "", province: a.province || "",
      postcode: a.postcode, note: a.note || "", is_default: a.is_default,
    });
    setEditing(a.id);
    setErr(null);
  };

  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      const body = { ...draft, label: draft.label || null, note: draft.note || null };
      const saved = editing === "new"
        ? await apiPost<SavedAddress>("/me/addresses", body)
        : await apiPatch<SavedAddress>(`/me/addresses/${editing}`, body);
      await load(saved.id);
      setEditing(null);
      setOpen(Boolean(manage));
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (a: SavedAddress) => {
    if (!confirm(`ลบที่อยู่${a.label ? ` "${a.label}"` : ""} ออกจากสมุด?`)) return;
    setBusy(true);
    try {
      await apiDelete(`/me/addresses/${a.id}`);
      await load();
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const setField = (k: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setDraft((d) => ({ ...d, [k]: e.target.value }));

  const selected = rows?.find((a) => a.id === selectedId) || null;

  if (rows === null) return <div className="ph" style={{ height: 96 }}>กำลังโหลดที่อยู่…</div>;

  // ---------- ฟอร์มเพิ่ม/แก้ไข ----------
  if (editing) {
    return (
      <div className="addr-form">
        <div className="row between" style={{ marginBottom: 8 }}>
          <b>{editing === "new" ? "เพิ่มที่อยู่ใหม่" : "แก้ไขที่อยู่"}</b>
          <button className="link-btn small" onClick={() => setEditing(null)}>ยกเลิก</button>
        </div>
        <div className="form-grid">
          <label className="field"><span>ชื่อผู้รับ *</span><input value={draft.receiver} onChange={setField("receiver")} placeholder="ชื่อ-นามสกุล" /></label>
          <label className="field"><span>เบอร์โทรศัพท์ *</span><input value={draft.phone} onChange={setField("phone")} placeholder="08X-XXX-XXXX" inputMode="tel" /></label>
          <label className="field span2"><span>ที่อยู่ *</span><input value={draft.address} onChange={setField("address")} placeholder="เลขที่ หมู่บ้าน/คอนโด ตึก ซอย ถนน" /></label>
          <AddressPicker
            postcode={draft.postcode}
            sub={draft.sub}
            district={draft.district}
            province={draft.province}
            onChange={(p) => setDraft((d) => ({ ...d, ...(p.postcode !== undefined && { postcode: p.postcode }), ...(p.sub !== undefined && { sub: p.sub }), ...(p.district !== undefined && { district: p.district }), ...(p.province !== undefined && { province: p.province }) }))}
          />
          <label className="field"><span>ป้ายกำกับ</span><input value={draft.label} onChange={setField("label")} placeholder="บ้าน · ที่ทำงาน" /></label>
          <label className="field"><span>จุดสังเกต</span><input value={draft.note} onChange={setField("note")} placeholder="เช่น ตึกสีเทา ฝากไว้กับนิติฯ" /></label>
        </div>
        <label className="row small" style={{ marginTop: 8 }}>
          <input type="checkbox" checked={draft.is_default} onChange={(e) => setDraft((d) => ({ ...d, is_default: e.target.checked }))} />
          ตั้งเป็นที่อยู่เริ่มต้น
        </label>
        {err && <div className="note err small" style={{ marginTop: 8 }}>{err}</div>}
        <button className="btn dark block" style={{ marginTop: 10 }} disabled={busy} onClick={save}>
          {busy ? "กำลังบันทึก…" : "บันทึกที่อยู่"}
        </button>
      </div>
    );
  }

  // ---------- ยังไม่มีที่อยู่เลย ----------
  if (!rows.length) {
    return (
      <div className="addr-empty">
        <Icon name="location_off" size={26} />
        <div><b>ยังไม่มีที่อยู่จัดส่ง</b><div className="small muted">เพิ่มไว้ครั้งเดียว ครั้งหน้าเลือกได้เลยไม่ต้องพิมพ์ใหม่</div></div>
        <button className="btn dark sm" onClick={startNew}><Icon name="add" size={16} /> เพิ่มที่อยู่</button>
      </div>
    );
  }

  // ---------- ใบที่เลือกอยู่ + รายการให้เปลี่ยน ----------
  return (
    <div className="addr-book">
      {selected && !open && !manage && (
        <div className="addr-current">
          <Icon name="location_on" size={20} />
          <div className="grow">
            <b>{selected.receiver} · {selected.phone}</b>
            {selected.label && <span className="addr-tag">{selected.label}</span>}
            {selected.is_default && <span className="addr-tag def">ค่าเริ่มต้น</span>}
            <div className="small muted">{selected.one_line}</div>
            {selected.note && <div className="tiny muted">หมายเหตุ: {selected.note}</div>}
          </div>
          <button className="link-btn small" onClick={() => setOpen(true)}>เปลี่ยน</button>
        </div>
      )}

      {open && (
        <div className="addr-list">
          {rows.map((a) => (
            <label key={a.id} className={"addr-row" + ((manage ? a.is_default : a.id === selectedId) ? " on" : "")}>
              <input
                type="radio"
                name="addr"
                checked={manage ? a.is_default : a.id === selectedId}
                onChange={async () => {
                  if (!manage) { onSelect(a); setOpen(false); return; }
                  setBusy(true);
                  try { await apiPost(`/me/addresses/${a.id}/default`); await load(a.id); }
                  catch (e) { setErr(errorMessage(e)); }
                  finally { setBusy(false); }
                }}
              />
              <div className="grow">
                <b>{a.receiver} · {a.phone}</b>
                {a.label && <span className="addr-tag">{a.label}</span>}
                {a.is_default && <span className="addr-tag def">ค่าเริ่มต้น</span>}
                <div className="small muted">{a.one_line}</div>
              </div>
              <span className="addr-acts">
                <button className="link-btn small" onClick={(e) => { e.preventDefault(); startEdit(a); }}>แก้ไข</button>
                <button className="link-btn small danger" disabled={busy} onClick={(e) => { e.preventDefault(); void remove(a); }}>ลบ</button>
              </span>
            </label>
          ))}
          {err && <div className="note err small">{err}</div>}
          <div className="row" style={{ gap: 8 }}>
            <button className="btn sm" onClick={startNew}><Icon name="add" size={16} /> เพิ่มที่อยู่ใหม่</button>
            {!manage && <button className="link-btn small" onClick={() => setOpen(false)}>ปิดรายการ</button>}
          </div>
        </div>
      )}
    </div>
  );
}
