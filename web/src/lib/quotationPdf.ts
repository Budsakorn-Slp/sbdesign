import { API_BASE, loadAuth } from "./api";

/** สร้างไฟล์ PDF ของใบเสนอราคาในเบราว์เซอร์
 *
 * ทำไมไม่ทำที่เซิร์ฟเวอร์: ตัวสร้าง PDF ฝั่ง Python วางสระ/วรรณยุกต์ภาษาไทยผิดตำแหน่ง
 * ตัวที่ทำได้ถูก (WeasyPrint/Chromium) ต้องลงโปรแกรมก้อนใหญ่บนเซิร์ฟเวอร์
 * ให้เบราว์เซอร์วาดหน้าเอกสารเดิม (ภาษาไทยถูกแน่นอน) แล้วแปลงเป็น PDF เลยง่ายและตรงกับที่เห็นที่สุด
 *
 * ทำไมไม่ใช้ iframe ชี้ไปที่หน้าเอกสารตรงๆ: หน้านั้นตั้ง X-Frame-Options: DENY ไว้ (กันเว็บปลอมเอาไปฝัง)
 * จึงดึง HTML มาเขียนลง iframe เปล่าของเราเอง พร้อม <base> ให้ลิงก์รูป/โลโก้ยังชี้ถูกที่
 *
 * ไฟล์ที่ได้เป็นภาพทั้งหน้า (เลือกคัดลอกข้อความไม่ได้) — พอสำหรับส่งให้ลูกค้าดู/พิมพ์
 */
export async function quotationPdf(no: string, token: string | null | undefined, withImages: boolean): Promise<Blob> {
  const [{ default: html2canvas }, { jsPDF }] = await Promise.all([import("html2canvas"), import("jspdf")]);

  const qs = new URLSearchParams();
  if (token) qs.set("t", token);
  if (withImages) qs.set("images", "1");
  qs.set("proxy", "1");   // โลโก้/รูปสินค้าผ่านเซิร์ฟเวอร์เรา ไม่งั้นวาดลงไฟล์ไม่ได้
  const docPath = `${API_BASE}/quotations/${no}/document`;
  const auth = loadAuth();
  const res = await fetch(`${docPath}?${qs.toString()}`, {
    headers: auth ? { Authorization: `Bearer ${auth.access_token}` } : {},
    credentials: "include",
  });
  if (!res.ok) throw new Error(res.status === 401 || res.status === 403 ? "ไม่มีสิทธิ์เปิดใบนี้" : "โหลดใบเสนอราคาไม่สำเร็จ");
  const html = (await res.text()).replace("<head>", `<head><base href="${location.origin}${docPath}">`);

  const frame = document.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;left:-10000px;top:0;width:900px;height:1400px;border:0;visibility:hidden";
  document.body.appendChild(frame);
  try {
    const doc = frame.contentDocument!;
    doc.open();
    doc.write(html);
    doc.close();
    await new Promise((r) => (doc.readyState === "complete" ? r(null) : frame.addEventListener("load", () => r(null), { once: true })));
    await doc.fonts?.ready;
    await Promise.all(Array.from(doc.images).map((img) => (img.complete ? null : new Promise((r) => { img.onload = img.onerror = () => r(null); }))));
    doc.querySelectorAll<HTMLElement>(".no-print").forEach((el) => (el.style.display = "none"));

    const body = doc.body;
    const scale = 2;
    const canvas = await html2canvas(body, { scale, useCORS: true, backgroundColor: "#ffffff", windowWidth: 900, logging: false });

    // จุดตัดหน้าที่ปลอดภัย = ขอบล่างของแถวตาราง/ข้อเงื่อนไข/กล่อง — ไม่ตัดกลางบรรทัด
    const top = body.getBoundingClientRect().top;
    const cuts = Array.from(body.querySelectorAll("tr, li, .box, .note-box, .staff, .terms, p"))
      .map((el) => Math.round((el.getBoundingClientRect().bottom - top) * scale))
      .sort((a, b) => a - b);

    const pdf = new jsPDF({ unit: "pt", format: "a4" });
    const pageW = pdf.internal.pageSize.getWidth();
    const pageH = pdf.internal.pageSize.getHeight();
    const margin = 24;
    const imgW = pageW - margin * 2;
    const pxPerPt = canvas.width / imgW;
    const maxSlice = Math.floor((pageH - margin * 2) * pxPerPt);

    let y = 0;
    let first = true;
    while (y < canvas.height - 2) {
      let end = Math.min(y + maxSlice, canvas.height);
      if (end < canvas.height) {
        const safe = cuts.filter((c) => c > y + maxSlice * 0.5 && c <= end).pop();
        if (safe) end = safe;
      }
      const slice = document.createElement("canvas");
      slice.width = canvas.width;
      slice.height = end - y;
      slice.getContext("2d")!.drawImage(canvas, 0, y, canvas.width, end - y, 0, 0, canvas.width, end - y);
      if (!first) pdf.addPage();
      pdf.addImage(slice.toDataURL("image/jpeg", 0.92), "JPEG", margin, margin, imgW, (end - y) / pxPerPt);
      first = false;
      y = end;
    }
    return pdf.output("blob");
  } finally {
    frame.remove();
  }
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
