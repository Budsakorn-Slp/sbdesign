import { useEffect, useState } from "react";
import type { CSSProperties, ReactNode } from "react";

type Props = {
  label?: ReactNode;
  ratio?: string;
  className?: string;
  style?: CSSProperties;
  /** ที่มาของรูป — ส่งได้หลายที่ จะไล่ลองตามลำดับจนกว่าจะมีอันโหลดขึ้น (ดู lib/images) */
  src?: string | string[] | null;
  alt?: string;
  /** รูปที่อยู่ในสายตาตั้งแต่เปิดหน้า (รูปสินค้าใบใหญ่/แบนเนอร์บนสุด)
   *
   *  ค่าปกติเป็น lazy ซึ่งเบราว์เซอร์จะถ่วงไว้ท้ายคิว ผลคือเห็นตัวหนังสือก่อนแล้วรูปค่อยโผล่
   *  ใบที่เห็นแน่ๆ ต้องสั่งโหลดทันทีและจัดลำดับความสำคัญให้สูง */
  priority?: boolean;
};

/** กรอบภาพแบบ wireframe (ลายทาง) — ถ้ามี src จะโชว์รูปจริงแทน
 *
 * รูปเสียแล้วไม่ตกกรอบทันที: ไล่ลองที่มาถัดไปก่อน (Magento ล่มก็ยังได้รูปจาก CDC)
 * หมดทุกที่แล้วค่อยกลับมาที่กรอบลายทาง
 */
export default function Placeholder({ label, ratio = "1 / 1", className, style, src, alt, priority }: Props) {
  const list = (Array.isArray(src) ? src : src ? [src] : []).filter(Boolean);
  const [i, setI] = useState(0);
  // เปลี่ยนสินค้าในการ์ดใบเดิม (แถวเลื่อน / เปลี่ยนหน้า) ต้องเริ่มไล่ใหม่ ไม่งั้นค้างที่ตัวสุดท้าย
  const key = list.join("|");
  useEffect(() => setI(0), [key]);

  if (i < list.length) {
    return (
      <div className={"img-frame" + (className ? " " + className : "")} style={{ aspectRatio: ratio, ...style }}>
        <img src={list[i]} alt={alt || ""} loading={priority ? "eager" : "lazy"}
             fetchPriority={priority ? "high" : "auto"} decoding="async"
             onError={() => setI((n) => n + 1)} />
      </div>
    );
  }
  return (
    <div className={"ph img" + (className ? " " + className : "")} style={{ aspectRatio: ratio, ...style }}>
      {label}
    </div>
  );
}
