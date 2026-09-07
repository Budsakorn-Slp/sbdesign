export function num(v: string | number | null | undefined): number {
  if (v === null || v === undefined) return 0;
  const n = typeof v === "number" ? v : parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

/** 24900 -> "24,900.-" (รูปแบบป้ายราคาตาม mockup) */
export function baht(v: string | number | null | undefined): string {
  return num(v).toLocaleString("en-US", { maximumFractionDigits: 0 }) + ".-";
}

/** 24900 -> "24,900 บาท" */
export function bahtWord(v: string | number | null | undefined): string {
  return num(v).toLocaleString("en-US", { maximumFractionDigits: 0 }) + " บาท";
}

const TH_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."];

/** "2026-09-15" -> "15 ก.ย." */
export function thDate(iso: string | null | undefined, withYear = false): string {
  if (!iso) return "-";
  const d = new Date(iso.length <= 10 ? iso + "T00:00:00" : iso);
  if (Number.isNaN(d.getTime())) return iso;
  const s = `${d.getDate()} ${TH_MONTHS[d.getMonth()]}`;
  return withYear ? `${s} ${(d.getFullYear() + 543) % 100}` : s;
}

/** "2026-09-07T09:46:00" -> "09:46" */
export function thTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" });
}

export function relTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  const diff = Math.round((Date.now() - d.getTime()) / 60000);
  if (diff < 1) return "เมื่อสักครู่";
  if (diff < 60) return `${diff} นาทีที่แล้ว`;
  if (diff < 60 * 24) return `${Math.round(diff / 60)} ชั่วโมงที่แล้ว`;
  if (diff < 60 * 48) return "เมื่อวาน";
  return `${Math.round(diff / 1440)} วันก่อน`;
}
