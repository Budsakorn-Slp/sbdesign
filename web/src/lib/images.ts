/** ที่มาของรูปสินค้า — ไล่ลองทีละที่ ไม่ให้กริดเหลือกล่องเปล่า
 *
 * รูปหลักมาจาก Magento (media.sbdesignsquare.com) ซึ่งล่ม/โดนบล็อก/ลิงก์เสียได้
 * ตัวสำรองคือ CDC ที่ตั้งชื่อไฟล์ตาม MATNR ตรงๆ — วัดแล้วครอบคลุมสินค้าที่มีรูปอยู่แล้ว ~70%
 * ที่เหลือตกไปที่กรอบ wireframe ของ Placeholder (ดีกว่าเอาโลโก้มาแปะ เพราะไม่หลอกว่ามีรูป)
 */
const CDC_BASE = "https://cdc.sbdsapp.com/images/";
const MAGENTO_OLD = "https://sbdesignsquare.com/media/";
const MAGENTO_CDN = "https://media.sbdesignsquare.com/media//";

/** ต้นทางเก็บลิงก์ไว้สองแบบ — แบบเว็บเก่าต้องชี้ไป CDN ไม่งั้นโหลดช้า/โดน redirect */
export function normalizeImageUrl(url: string): string {
  if (url.includes(".jpeg")) return url;
  return url.replace(MAGENTO_OLD, MAGENTO_CDN);
}

/** ลำดับที่จะลอง: รูปที่เก็บไว้ → รูปตาม MATNR ที่ CDC · ตัดตัวซ้ำ/ตัวว่างออกให้แล้ว */
export function imageSources(matnr: string, imageUrl?: string | null): string[] {
  const out = imageUrl ? [normalizeImageUrl(imageUrl)] : [];
  if (matnr) out.push(`${CDC_BASE}${matnr}_1.jpg`);
  return [...new Set(out)];
}
