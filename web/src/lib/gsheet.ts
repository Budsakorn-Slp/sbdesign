import { API_BASE, ApiError, apiPost, loadAuth } from "./api";
import { downloadBlob } from "./quotationPdf";

/** เปิดใบเสนอราคาเป็น Google Sheet
 *
 * ทางหลัก: backend สร้างชีตใน Shared Drive ของบริษัท แล้วแชร์สิทธิ์แก้ไขให้คนที่กด
 *   (ต้องตั้ง service account — ยังไม่ได้ตั้ง หลังบ้านตอบ 501)
 * ทางที่ใช้ตอนนี้: ดาวน์โหลดไฟล์ Excel (หน้าตาเดียวกับใบ PDF) แล้วเปิด Google Drive ให้
 *   พนักงานลากไฟล์ลงไป แล้วคลิกขวา → เปิดด้วย Google ชีต ได้ชีตที่มีหัวใบ/กรอบ/ยอดรวมครบ
 *   (เดิมใช้สูตร IMPORTDATA ได้แค่ตารางเรียบ และต้องเอาลิงก์ที่มี token ของใบไปวางในชีต — เลิกใช้)
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
    const auth = loadAuth();
    const res = await fetch(`${API_BASE}/quotations/${no}/export?format=xlsx${token ? `&t=${token}` : ""}`, {
      headers: auth ? { Authorization: `Bearer ${auth.access_token}` } : {},
      credentials: "include",
    });
    if (!res.ok) {
      tab?.close();
      throw new Error("ดาวน์โหลดไฟล์ Excel ไม่สำเร็จ");
    }
    downloadBlob(await res.blob(), `${no}.xlsx`);
    if (tab) tab.location.href = "https://drive.google.com/drive/my-drive";
    return `ดาวน์โหลด ${no}.xlsx แล้ว และเปิด Google Drive ให้ในแท็บใหม่ — ลากไฟล์ลงในหน้า Drive แล้วคลิกขวาที่ไฟล์ → เปิดด้วย → Google ชีต`;
  }
}
