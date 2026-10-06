import { API_BASE, loadAuth } from "./api";

/** ใบเสนอราคาเป็นไฟล์ PDF / รูปภาพ — สร้างในเบราว์เซอร์
 *
 * ทำไมไม่ทำที่เซิร์ฟเวอร์: ตัวสร้าง PDF ฝั่ง Python วางสระ/วรรณยุกต์ภาษาไทยผิดตำแหน่ง
 * ตัวที่ทำได้ถูก (WeasyPrint/Chromium) ต้องลงโปรแกรมก้อนใหญ่บนเซิร์ฟเวอร์
 * ให้เบราว์เซอร์วาดหน้าเอกสารเดิม แล้วแปลงเป็นไฟล์เลยง่ายและตรงกับที่เห็นที่สุด
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

// ฟอนต์ของหน้าเอกสาร (ดู api/quotation_doc.py) — ต้องโหลดใน "หน้าเว็บหลัก" ด้วย
// ตัววาด (html2canvas) จัดตำแหน่งคำตามหน้าเอกสาร แต่เขียนตัวอักษรลง canvas ของหน้าหลัก
// หน้าหลักใช้ฟอนต์ Anuphan ไม่มี Noto Sans Thai → วาดด้วยฟอนต์อื่นในตำแหน่งของฟอนต์เดิม
// = สระ/วรรณยุกต์เหลื่อม คำซ้อนกัน (เจอจริงในรูปที่ดาวน์โหลด)
const DOC_FONT = "Noto Sans Thai";
const DOC_FONT_CSS = "https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@400;600;700&display=swap";

async function ensureDocFont(): Promise<void> {
  if (!document.querySelector(`link[data-doc-font]`)) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = DOC_FONT_CSS;
    link.dataset.docFont = "1";
    document.head.appendChild(link);
    await new Promise((r) => { link.onload = link.onerror = () => r(null); });
  }
  await Promise.all(["400", "600", "700"].map((w) => document.fonts.load(`${w} 16px "${DOC_FONT}"`, "กขค").catch(() => null)));
}

/** วาดใบทั้งใบเป็นภาพยาวหนึ่งภาพ + ตำแหน่งที่ตัดหน้าได้โดยไม่ผ่ากลางบรรทัด */
async function renderCanvas(no: string, token: string | null | undefined, withImages: boolean): Promise<{ canvas: HTMLCanvasElement; cuts: number[] }> {
  const [{ default: html2canvas }] = await Promise.all([import("html2canvas"), ensureDocFont()]);

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
    await Promise.all(["400", "600", "700"].map((w) => doc.fonts?.load(`${w} 16px "${DOC_FONT}"`, "กขค").catch(() => null)));
    await Promise.all(Array.from(doc.images).map((img) => (img.complete ? null : new Promise((r) => { img.onload = img.onerror = () => r(null); }))));
    doc.querySelectorAll<HTMLElement>(".no-print").forEach((el) => (el.style.display = "none"));

    // ขยายกรอบให้สูงเท่าเนื้อหาก่อนวาด — ตัววาดจับภาพสูงเท่ากรอบหน้าต่าง ไม่ใช่เท่าเนื้อหา
    // ปล่อยกรอบสูง 1400 ไว้ ใบสั้นได้ที่ว่างขาวท้ายรูปครึ่งภาพ ใบยาวโดนตัดหาย
    // และอัตราส่วนภาพ:หน้าเพี้ยน ทำให้จุดตัดหน้า PDF ไปผ่ากลางบรรทัด
    const fullH = Math.ceil(doc.documentElement.scrollHeight);
    frame.style.height = `${fullH}px`;
    void doc.body.offsetHeight;   // บังคับจัดหน้าใหม่ทันที (ไม่ใช้รอเฟรม — แท็บที่ไม่ได้แสดงอยู่จะไม่มีเฟรม ค้างตลอด)

    const body = doc.body;
    const box = body.getBoundingClientRect();
    const canvas = await html2canvas(body, {
      scale: SCALE, useCORS: true, backgroundColor: "#ffffff", logging: false,
      windowWidth: 900, windowHeight: fullH, height: Math.ceil(box.height),
    });

    // จุดตัดหน้าที่ปลอดภัย = ขอบล่างของแถวตาราง/ข้อเงื่อนไข/กล่อง
    // คูณด้วยอัตราส่วนจริง (ความสูงภาพ ÷ ความสูงหน้า) ไม่ใช่ค่า scale ตายตัว
    // ภาพจริงสูงไม่เท่าหน้า × scale พอดี ใช้ค่าตายตัวแล้วจุดตัดเลื่อนไปผ่ากลางบรรทัดข้างล่าง
    const ratio = canvas.height / Math.max(box.height, 1);
    const cuts = Array.from(body.querySelectorAll("tr, li, .hdr, .parties, .who, .note-box, .terms > b, p"))
      .map((el) => Math.round((el.getBoundingClientRect().bottom - box.top) * ratio) + 2)
      .sort((a, b) => a - b);

    // ตัดที่ท้ายเนื้อหาจริง — body สูงเต็มกรอบ iframe ไม่งั้นท้ายรูปเป็นที่ว่างขาวยาวครึ่งภาพ
    const contentBottom = Math.max(...Array.from(body.children).map((el) => el.getBoundingClientRect().bottom)) - box.top;
    const keep = Math.min(canvas.height, Math.ceil((contentBottom + 12) * ratio));
    if (keep < canvas.height - 4) {
      const [trim, ctx] = blank(canvas.width, keep);
      ctx.drawImage(canvas, 0, 0, canvas.width, keep, 0, 0, canvas.width, keep);
      return { canvas: trim, cuts: cuts.filter((c) => c < keep) };
    }
    return { canvas, cuts };
  } finally {
    frame.remove();
  }
}

function blank(w: number, h: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const ctx = c.getContext("2d")!;
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, w, h);
  return [c, ctx];
}

export async function quotationPdf(no: string, token: string | null | undefined, withImages: boolean): Promise<Blob> {
  const [{ canvas, cuts }, { jsPDF }] = await Promise.all([renderCanvas(no, token, withImages), import("jspdf")]);
  const imgW = PAGE_W_PT - MARGIN_PT * 2;
  const pxPerPt = canvas.width / imgW;
  const maxSlice = Math.floor((PAGE_H_PT - MARGIN_PT * 2) * pxPerPt);
  const pdf = new jsPDF({ unit: "pt", format: "a4" });
  let y = 0;
  let first = true;
  while (y < canvas.height - 2) {
    let end = Math.min(y + maxSlice, canvas.height);
    if (end < canvas.height) {
      const safe = cuts.filter((c) => c > y + maxSlice * 0.4 && c <= end).pop();
      if (safe) end = safe;
    }
    const [slice, ctx] = blank(canvas.width, end - y);
    ctx.drawImage(canvas, 0, y, canvas.width, end - y, 0, 0, canvas.width, end - y);
    if (!first) pdf.addPage();
    pdf.addImage(slice.toDataURL("image/jpeg", 0.92), "JPEG", MARGIN_PT, MARGIN_PT, imgW, (end - y) / pxPerPt);
    first = false;
    y = end;
  }
  return pdf.output("blob");
}

/** รูปภาพเดียวทั้งใบ (ยาวตามเนื้อหา มีขอบขาว) — ส่งเข้า LINE แล้วเห็นใบในแชตทันที ไม่ต้องกดเปิดไฟล์ */
export async function quotationImage(no: string, token: string | null | undefined, withImages: boolean): Promise<File> {
  const { canvas } = await renderCanvas(no, token, withImages);
  const pad = Math.round(MARGIN_PT * canvas.width / (PAGE_W_PT - MARGIN_PT * 2));
  const [out, ctx] = blank(canvas.width + pad * 2, canvas.height + pad * 2);
  ctx.drawImage(canvas, pad, pad);
  const blob: Blob = await new Promise((r, x) => out.toBlob((b) => (b ? r(b) : x(new Error("สร้างรูปไม่สำเร็จ"))), "image/jpeg", 0.9));
  return new File([blob], `${no}.jpg`, { type: "image/jpeg" });
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
