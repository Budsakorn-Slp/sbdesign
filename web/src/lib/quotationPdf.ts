import { API_BASE, loadAuth } from "./api";

/** ใบเสนอราคาเป็นไฟล์ PDF / รูปภาพ — สร้างในเบราว์เซอร์
 *
 * ทำไมไม่ทำที่เซิร์ฟเวอร์: ตัวสร้าง PDF ฝั่ง Python วางสระ/วรรณยุกต์ภาษาไทยผิดตำแหน่ง
 * ตัวที่ทำได้ถูก (WeasyPrint/Chromium) ต้องลงโปรแกรมก้อนใหญ่บนเซิร์ฟเวอร์
 * ให้เบราว์เซอร์วาดหน้าเอกสารเดิม (ภาษาไทยถูกแน่นอน) แล้วแปลงเป็นไฟล์เลยง่ายและตรงกับที่เห็นที่สุด
 *
 * ทำไมไม่ใช้ iframe ชี้ไปที่หน้าเอกสารตรงๆ: หน้านั้นตั้ง X-Frame-Options: DENY ไว้ (กันเว็บปลอมเอาไปฝัง)
 * จึงดึง HTML มาเขียนลง iframe เปล่าของเราเอง พร้อม <base> ให้ลิงก์รูป/โลโก้ยังชี้ถูกที่
 *
 * ไฟล์ที่ได้เป็นภาพทั้งหน้า (เลือกคัดลอกข้อความไม่ได้) — พอสำหรับส่งให้ลูกค้าดู/พิมพ์
 */

const SCALE = 2;
const PAGE_W_PT = 595.28;   // A4
const PAGE_H_PT = 841.89;
const MARGIN_PT = 24;

/** วาดใบทั้งใบเป็นภาพยาวหนึ่งภาพ แล้วตัดเป็นหน้า A4 ตรงขอบแถว (ไม่ตัดกลางบรรทัด) */
async function renderPages(no: string, token: string | null | undefined, withImages: boolean): Promise<HTMLCanvasElement[]> {
  const { default: html2canvas } = await import("html2canvas");

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
    const canvas = await html2canvas(body, { scale: SCALE, useCORS: true, backgroundColor: "#ffffff", windowWidth: 900, logging: false });

    // จุดตัดหน้าที่ปลอดภัย = ขอบล่างของแถวตาราง/ข้อเงื่อนไข/กล่อง — ไม่ตัดกลางบรรทัด
    const top = body.getBoundingClientRect().top;
    const cuts = Array.from(body.querySelectorAll("tr, li, .hdr, .parties, .who, .note-box, .terms, p"))
      .map((el) => Math.round((el.getBoundingClientRect().bottom - top) * SCALE))
      .sort((a, b) => a - b);

    const pxPerPt = canvas.width / (PAGE_W_PT - MARGIN_PT * 2);
    const maxSlice = Math.floor((PAGE_H_PT - MARGIN_PT * 2) * pxPerPt);
    const pages: HTMLCanvasElement[] = [];
    let y = 0;
    while (y < canvas.height - 2) {
      let end = Math.min(y + maxSlice, canvas.height);
      if (end < canvas.height) {
        const safe = cuts.filter((c) => c > y + maxSlice * 0.5 && c <= end).pop();
        if (safe) end = safe;
      }
      const slice = document.createElement("canvas");
      slice.width = canvas.width;
      slice.height = end - y;
      const ctx = slice.getContext("2d")!;
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, slice.width, slice.height);
      ctx.drawImage(canvas, 0, y, canvas.width, end - y, 0, 0, canvas.width, end - y);
      pages.push(slice);
      y = end;
    }
    return pages;
  } finally {
    frame.remove();
  }
}

export async function quotationPdf(no: string, token: string | null | undefined, withImages: boolean): Promise<Blob> {
  const [pages, { jsPDF }] = await Promise.all([renderPages(no, token, withImages), import("jspdf")]);
  const pdf = new jsPDF({ unit: "pt", format: "a4" });
  const imgW = PAGE_W_PT - MARGIN_PT * 2;
  pages.forEach((pg, i) => {
    if (i) pdf.addPage();
    pdf.addImage(pg.toDataURL("image/jpeg", 0.92), "JPEG", MARGIN_PT, MARGIN_PT, imgW, pg.height / (pg.width / imgW));
  });
  return pdf.output("blob");
}

/** รูปภาพหน้าละไฟล์ (JPG ขอบขาวเท่ากับหน้า A4) — ส่งเข้า LINE แล้วเห็นใบในแชตทันที ไม่ต้องกดเปิดไฟล์ */
export async function quotationImages(no: string, token: string | null | undefined, withImages: boolean): Promise<File[]> {
  const pages = await renderPages(no, token, withImages);
  const pad = Math.round(MARGIN_PT * (pages[0]?.width ?? 0) / (PAGE_W_PT - MARGIN_PT * 2));
  const files: File[] = [];
  for (let i = 0; i < pages.length; i++) {
    const pg = pages[i];
    const out = document.createElement("canvas");
    out.width = pg.width + pad * 2;
    out.height = pg.height + pad * 2;
    const ctx = out.getContext("2d")!;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, out.width, out.height);
    ctx.drawImage(pg, pad, pad);
    const blob: Blob = await new Promise((r, x) => out.toBlob((b) => (b ? r(b) : x(new Error("สร้างรูปไม่สำเร็จ"))), "image/jpeg", 0.9));
    const suffix = pages.length > 1 ? `-${i + 1}` : "";
    files.push(new File([blob], `${no}${suffix}.jpg`, { type: "image/jpeg" }));
  }
  return files;
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
