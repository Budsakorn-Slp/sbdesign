import { useMemo, useState } from "react";
import Icon from "./Icon";
import type { DeliverySlot } from "../lib/types";

/** ปฏิทินเลือกวันจัดส่ง — เลือกแค่ "วัน" ไม่ต้องเลือกเช้า/บ่าย
 *
 *  ทีมคิวจัดส่งเป็นคนซอยรอบเองอยู่แล้ว การให้พนักงานหน้าร้านเลือกช่วงเวลาด้วย
 *  ทำให้ต้องตัดสินใจเพิ่มโดยไม่มีข้อมูล และหน้าจอยาวเป็นสองเท่าเพราะหนึ่งวันมีสองปุ่ม
 *
 *  เบื้องหลังคิวยังเก็บเป็นรอบเช้า/บ่ายเหมือนเดิม กดวันไหนก็จองรอบที่ยังว่างของวันนั้นให้
 *  (เอารอบเช้าก่อน) — ถ้าวันหลังทีมคิวอยากให้เลือกช่วงเวลาอีก ข้อมูลยังอยู่ครบ
 */
type Props = {
  slots: DeliverySlot[];
  heldId: string | null;
  busy: boolean;
  /** คืน true ถ้าจองสำเร็จ — ปฏิทินเอาไปบอกผลให้พนักงานเห็นตรงปุ่ม */
  onPick: (slotId: string) => Promise<boolean> | boolean;
};

const DOW = ["อา", "จ", "อ", "พ", "พฤ", "ศ", "ส"];
/** 2026-10-05 -> "5 ต.ค." — ใช้ทวนกับลูกค้าก่อนกดจอง */
const thDay = (iso: string) => {
  const d = new Date(iso + "T00:00:00");
  return `${d.getDate()} ${["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."][d.getMonth()]}`;
};
const MONTHS = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
  "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"];

type Day = { remaining: number; pick: string | null; held: boolean };

export default function SlotCalendar({ slots, heldId, busy, onPick }: Props) {
  // รวมรอบเช้า+บ่ายของวันเดียวกันเป็นบรรทัดเดียว · เลือกรอบที่ยังว่างไว้ให้พร้อมกด
  const byDay = useMemo(() => {
    const m = new Map<string, Day>();
    for (const s of [...slots].sort((a, b) => a.period.localeCompare(b.period))) {
      const d = m.get(s.date) || { remaining: 0, pick: null, held: false };
      d.remaining += Math.max(0, s.remaining);
      d.held = d.held || s.held_by_this_cart;
      if (!d.pick && (s.remaining > 0 || s.held_by_this_cart)) d.pick = s.id;
      m.set(s.date, d);
    }
    return m;
  }, [slots]);

  // เลือกวันก่อน แล้วค่อยกดจอง — กดวันแล้วจองทันทีคือการยิงคำสั่งจากการกดพลาดหนึ่งครั้ง
  // และไม่มีจังหวะให้ทวนกับลูกค้าว่า "วันนี้นะครับ" ก่อนคิวถูกกันไว้จริง
  const [sel, setSel] = useState<string | null>(null);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  const dates = [...byDay.keys()].sort();
  const first = dates[0] ? new Date(dates[0] + "T00:00:00") : new Date();
  const [cursor, setCursor] = useState(new Date(first.getFullYear(), first.getMonth(), 1));

  const y = cursor.getFullYear();
  const mo = cursor.getMonth();
  const lead = new Date(y, mo, 1).getDay();            // ช่องว่างก่อนวันที่ 1
  const days = new Date(y, mo + 1, 0).getDate();
  const iso = (d: number) => `${y}-${String(mo + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;

  // เดือนที่ไม่มีคิวเลยให้กดข้ามได้ แต่ไม่ต้องให้เลื่อนไปไกลเกินช่วงที่ระบบเปิดคิวจริง
  const inRange = (delta: number) => {
    const t = new Date(y, mo + delta, 1);
    const lo = new Date(first.getFullYear(), first.getMonth(), 1);
    const last = dates.length ? new Date(dates[dates.length - 1] + "T00:00:00") : first;
    const hi = new Date(last.getFullYear(), last.getMonth(), 1);
    return t >= lo && t <= hi;
  };

  return (
    <div className="cal">
      <div className="cal-head">
        <button type="button" className="icon-btn" disabled={!inRange(-1)} onClick={() => setCursor(new Date(y, mo - 1, 1))} aria-label="เดือนก่อนหน้า">
          <Icon name="chevron_left" size={20} />
        </button>
        <b>{MONTHS[mo]} {y + 543}</b>
        <button type="button" className="icon-btn" disabled={!inRange(1)} onClick={() => setCursor(new Date(y, mo + 1, 1))} aria-label="เดือนถัดไป">
          <Icon name="chevron_right" size={20} />
        </button>
      </div>

      <div className="cal-grid">
        {DOW.map((d) => <div key={d} className="cal-dow">{d}</div>)}
        {Array.from({ length: lead }, (_, i) => <div key={`x${i}`} />)}
        {Array.from({ length: days }, (_, i) => {
          const n = i + 1;
          const info = byDay.get(iso(n));
          if (!info) return <div key={n} className="cal-day off">{n}</div>;
          const full = info.remaining <= 0 && !info.held;
          const on = info.held || (heldId != null && info.pick === heldId);
          const picked = sel === iso(n) && !on;
          return (
            <button
              key={n}
              type="button"
              className={"cal-day" + (on ? " on" : picked ? " sel" : full ? " full" : " free")}
              disabled={busy || saving || full || !info.pick}
              onClick={() => { setSel(iso(n)); setResult(null); }}
              title={on ? "จองไว้แล้ว" : full ? "คิวเต็ม" : `คิวว่าง ${info.remaining}`}
            >
              <span className="cal-n">{n}</span>
              <span className="cal-tag">{on ? "จองแล้ว" : full ? "เต็ม" : "ว่าง"}</span>
            </button>
          );
        })}
      </div>

      {/* แถบยืนยัน — โผล่เมื่อเลือกวันแล้ว บอกวันที่เลือกให้ทวนกับลูกค้าก่อนกดจองจริง */}
      {sel && (
        <div className="cal-confirm">
          <span>เลือกวันที่ <b>{thDay(sel)}</b> · คิวว่าง {byDay.get(sel)?.remaining ?? 0}</span>
          <button className="link-btn small" type="button" disabled={saving} onClick={() => { setSel(null); setResult(null); }}>
            ยกเลิก
          </button>
          <button
            className="btn dark sm"
            type="button"
            disabled={saving || busy}
            onClick={async () => {
              const id = byDay.get(sel)?.pick;
              if (!id) return;
              setSaving(true);
              setResult(null);
              try {
                const ok = await onPick(id);
                setResult(ok
                  ? { ok: true, text: `จองคิววันที่ ${thDay(sel)} เรียบร้อย` }
                  : { ok: false, text: "จองไม่สำเร็จ — คิวอาจเต็มไปแล้ว ลองเลือกวันอื่น" });
                if (ok) setSel(null);
              } finally {
                setSaving(false);
              }
            }}
          >
            {saving ? "กำลังจอง…" : "จองคิววันนี้"}
          </button>
        </div>
      )}
      {result && <div className={"cal-result " + (result.ok ? "ok" : "no")}>{result.text}</div>}

      <div className="cal-legend">
        <span><i className="free" /> เปิดรับคิว</span>
        <span><i className="full" /> คิวเต็ม</span>
        <span><i className="sel" /> วันที่กำลังเลือก</span>
        <span><i className="on" /> จองแล้ว</span>
      </div>
    </div>
  );
}
