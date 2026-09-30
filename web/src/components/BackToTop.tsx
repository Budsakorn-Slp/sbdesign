import { useEffect, useState } from "react";
import Icon from "./Icon";
import { useLang } from "../lib/i18n";

/** ปุ่มลอย "กลับขึ้นบนสุด" — โผล่เมื่อเลื่อนลงไปไกลแล้ว
 *
 *  หน้ารายการสินค้าโหลดต่อไปเรื่อยๆ (infinite scroll) เลื่อนดูไป 200 ใบแล้วจะกลับขึ้นไป
 *  เปลี่ยนตัวกรองทีต้องปัดขึ้นเองยาวมาก ปุ่มนี้เลยจำเป็นกว่าหน้าอื่น
 */
const SHOW_AFTER = 600; // px — ประมาณหนึ่งจอครึ่ง ถ้าน้อยกว่านี้ปุ่มจะเด้งขึ้นมากวนตั้งแต่ยังไม่ทันเลื่อน

export default function BackToTop() {
  const [show, setShow] = useState(false);
  const { t } = useLang();

  useEffect(() => {
    // อ่าน scrollY ตรงนี้ทีเดียวแล้วส่งเข้า setState — ถ้าไปอ่านข้างใน updater
    // React อาจเรียกทีหลังตอนเลื่อนไปไกลแล้ว ปุ่มจะค้างผิดสถานะ (เคยเจอกับหัวเว็บ)
    const onScroll = () => {
      const y = window.scrollY;
      setShow((on) => (on ? y > SHOW_AFTER / 2 : y > SHOW_AFTER));
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  if (!show) return null;
  return (
    <button
      className="to-top"
      // ไม่ใช้ behavior:"smooth" — บางเบราว์เซอร์ไม่ขยับเลย (เจอกับตัว ทั้ง scrollBy และ scrollTo)
      // กระโดดขึ้นทันทีเชื่อถือได้กว่า และเป็นสิ่งที่ผู้ใช้ต้องการอยู่แล้วคือ "พาไปบนสุด"
      onClick={() => window.scrollTo(0, 0)}
      aria-label={t("กลับขึ้นบนสุด")}
      title={t("กลับขึ้นบนสุด")}
    >
      <Icon name="keyboard_arrow_up" size={24} />
    </button>
  );
}
