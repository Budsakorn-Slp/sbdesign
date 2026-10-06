/** กันหน้าขาวหลัง deploy เวอร์ชันใหม่
 *
 * โค้ดแต่ละหน้าแยกเป็นไฟล์ชื่อติด hash (SalesPage-Cdjabvzv.js) — build ใหม่ทีไรชื่อเปลี่ยน
 * แท็บที่เปิดค้างไว้ก่อน deploy ยังจำชื่อเก่า พอเปลี่ยนหน้าก็ไปขอไฟล์ที่ไม่มีแล้ว
 * เซิร์ฟเวอร์ตอบ index.html กลับมาแทน (SPA fallback) → โหลดโค้ดหน้าไม่ขึ้น → React ทั้งต้นพัง = จอขาว
 * ผู้ใช้ต้องกดรีเฟรชเองถึงจะหาย
 *
 * แก้: จับจังหวะโหลดโค้ดหน้าไม่ขึ้น แล้วรีโหลดหน้าเดิมให้เองหนึ่งครั้ง (ได้ index.html ตัวใหม่ที่รู้ชื่อไฟล์ใหม่)
 * จำเวลาไว้กันวนรีโหลดไม่จบ ถ้าเซิร์ฟเวอร์พังจริงๆ
 */
const KEY = "sb_chunk_reload_at";

export function reloadForNewVersion(): boolean {
  try {
    const last = Number(sessionStorage.getItem(KEY) || 0);
    if (Date.now() - last < 30_000) return false;   // เพิ่งรีโหลดไปแล้ว ยังพังอยู่ = ไม่ใช่เรื่องเวอร์ชัน
    sessionStorage.setItem(KEY, String(Date.now()));
  } catch {
    /* sessionStorage ใช้ไม่ได้ (โหมดส่วนตัวบางเบราว์เซอร์) — รีโหลดได้แต่กันวนไม่ได้ ยอมรับ */
  }
  window.location.reload();
  return true;
}

export function isChunkError(e: unknown): boolean {
  const m = e instanceof Error ? `${e.name} ${e.message}` : String(e);
  return /dynamically imported module|Importing a module script failed|Failed to fetch|ChunkLoadError|Unable to preload|MIME type/i.test(m);
}

export function installStaleChunkGuard(): void {
  // Vite ยิง event นี้เมื่อโหลดโค้ดหน้าที่แยกไฟล์ไว้ไม่ขึ้น
  window.addEventListener("vite:preloadError", (ev) => {
    if (reloadForNewVersion()) ev.preventDefault();
  });
  window.addEventListener("unhandledrejection", (ev) => {
    if (isChunkError(ev.reason)) reloadForNewVersion();
  });
}
