import { API_BASE, ApiError, apiPost } from "./api";

/** เปิดใบเสนอราคาเป็น Google Sheet
 *
 * ทางหลัก: backend สร้างชีตใน Shared Drive ของบริษัท แล้วแชร์สิทธิ์แก้ไขให้คนที่กด (ต้องตั้ง service account)
 * ทางสำรอง (ยังไม่ได้ตั้ง): เปิดชีตเปล่า + คัดลอกสูตร IMPORTDATA ไว้ให้วางที่ช่อง A1
 *   Google ดึงไฟล์ CSV ของใบนี้ผ่านลิงก์ที่มี token — ใช้ได้เฉพาะเว็บที่ออนไลน์ (localhost ใช้ไม่ได้)
 *
 * เปิดแท็บก่อนแล้วค่อยใส่ URL — ถ้ารอผลจาก API ก่อนค่อย window.open เบราว์เซอร์จะบล็อกว่าเป็น popup
 */
export async function openGoogleSheet(no: string, token: string | null | undefined): Promise<string> {
  const tab = window.open("about:blank", "_blank");
  try {
    const r = await apiPost<{ url: string }>(`/quotations/${no}/google-sheet`, {});
    if (tab) tab.location.href = r.url;
    else window.location.href = r.url;
    return "สร้าง Google Sheet แล้ว — แชร์สิทธิ์แก้ไขให้อีเมลของคุณ";
  } catch (e) {
    if (!(e instanceof ApiError && e.status === 501)) {
      tab?.close();
      throw e;
    }
    const src = `${location.origin}${API_BASE}/quotations/${no}/export?format=csv&bom=0${token ? `&t=${token}` : ""}`;
    const formula = `=IMPORTDATA("${src}")`;
    try {
      await navigator.clipboard.writeText(formula);
    } catch {
      /* บางเบราว์เซอร์ไม่ให้เข้าคลิปบอร์ด — ข้อความข้างล่างมีสูตรให้คัดลอกเองอยู่แล้ว */
    }
    if (tab) tab.location.href = "https://sheets.new";
    return `เปิดชีตใหม่แล้ว — คลิกช่อง A1 แล้วกดวาง (Ctrl+V) ข้อมูลใบจะดึงเข้ามาเอง · สูตร: ${formula}`;
  }
}
