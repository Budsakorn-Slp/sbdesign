import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Lang = "th" | "en";

/** ข้อความในส่วนที่เราเขียนเอง (ปุ่ม ป้าย หัวข้อ) — ข้อมูลสินค้า/หมวดมาจากฐาน ไม่ได้อยู่ในนี้
 *
 *  ยังไม่ครบทั้งเว็บ ตอนนี้ครอบคลุมส่วนที่เห็นทุกหน้า (หัวเว็บ ท้ายเว็บ ตะกร้า ค้นหา)
 *  หน้าอื่นยังเป็นไทยอยู่ ถ้าเจอคำที่ยังไม่ได้แปล t() จะคืนข้อความไทยเดิมให้ ไม่ขึ้นเป็นรหัสเปล่า
 */
const EN: Record<string, string> = {
  // หัวเว็บ
  "หน้าแรก": "Home",
  "สินค้าทั้งหมด": "All Products",
  "แบรนด์": "Brands",
  "สินค้าใหม่": "New In",
  "สินค้าตัวโชว์": "Display Items",
  "ค้นหาสินค้า แบรนด์ หรือรหัสสินค้า": "Search products, brands or codes",
  "ทั้งหมด": "All",
  "เข้าสู่ระบบ": "Sign in",
  "ออก": "Sign out",
  "ที่อยู่จัดส่ง": "Deliver to",
  "เลือกที่อยู่จัดส่ง": "Select address",
  "รับที่สาขา": "Pick up at",
  "เลือกสาขา": "Select branch",
  "ค้นหาสาขา": "Find a store",
  "ศูนย์ช่วยเหลือ": "Help centre",
  "บัญชีของฉัน": "My account",
  "ไม่เลือกสาขา": "No branch",
  "พ้อยท์": "points",
  "พนักงานขาย": "Sales",
  "ผู้จัดการ": "Manager",
  "แอดมิน": "Admin",
  "รหัสไปรษณีย์": "Postcode",
  "หมวดย่อยของ": "Categories in",
  "หมวดหมู่ทั้งหมด": "All categories",
  "แบรนด์ทั้งหมด": "All brands",
  "ดูสินค้าทั้งหมด": "Shop all",
  "ติดตามเรา": "Follow us",

  // ท้ายเว็บ
  "ร้านค้าออนไลน์": "Online store",
  "เกี่ยวกับเรา": "About us",
  "ติดต่อ SB Design Square": "Contact SB Design Square",
  "รับข่าวสารก่อนใคร": "Be the first to know",
  "สมัครสมาชิก": "Sign up",
  "บริการหลังการขาย ซ่อม/เคลม": "After-sales service",
  "การตั้งค่าคุกกี้": "Cookie settings",

  // ค้นหา / รายการสินค้า
  "แนะนำ": "Recommended",
  "ขายดี": "Best sellers",
  "มาใหม่": "New arrivals",
  "ราคาต่ำ → สูง": "Price: low to high",
  "ราคาสูง → ต่ำ": "Price: high to low",
  "ส่วนลดมากสุด": "Biggest discount",
  "พร้อมส่ง": "In stock",
  "ลดราคา": "On sale",
  "มีรูปสินค้า": "Has photo",
  "ตัวกรอง": "Filters",
  "ล้างทั้งหมด": "Clear all",
  "ล้างตัวกรองทั้งหมด": "Clear all filters",
  "ดูเพิ่มเติม": "Load more",
  "กำลังโหลด…": "Loading…",
  "แสดงครบแล้ว": "That's everything",
  "ไม่พบสินค้า": "No products found",
  "กำลังค้นหา…": "Searching…",
  "ดูทั้งหมด": "See all",

  // การ์ดสินค้า / ตะกร้า
  "ลงตะกร้า": "Add to cart",
  "ซื้อเลย": "Buy now",
  "พรีออเดอร์": "Pre-order",
  "สินค้าหมด": "Out of stock",
  "ตะกร้าสินค้า": "Shopping cart",
  "สั่งซื้อสินค้า": "Checkout",
  "ยอดรวมทั้งหมด": "Total",
  "ค่าจัดส่ง": "Shipping",
  "ยอดสั่งซื้อ": "Subtotal",
  "จำนวน": "Qty",
  "ราคา": "Price",
  "สมาชิก": "Member",

  // ทั่วไป
  "กลับขึ้นบนสุด": "Back to top",
  "กลับหน้าแรก": "Back to home",
  "ไม่พบหน้านี้": "Page not found",
  "บาท": "THB",
};

const DICTS: Record<Lang, Record<string, string>> = { th: {}, en: EN };
const KEY = "sb.lang";

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (s: string) => string };
const LangCtx = createContext<Ctx>({ lang: "th", setLang: () => {}, t: (s) => s });

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    try {
      return localStorage.getItem(KEY) === "en" ? "en" : "th";
    } catch {
      // โหมดส่วนตัวของบางเบราว์เซอร์อ่าน localStorage ไม่ได้ — ใช้ไทยเป็นค่าตั้งต้นไป
      return "th";
    }
  });

  const setLang = (l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(KEY, l);
    } catch {
      /* จำไม่ได้ก็ไม่เป็นไร แค่ไม่ค้างข้ามรอบเปิด */
    }
  };

  // บอกภาษาให้เบราว์เซอร์รู้ด้วย — มีผลกับการตัดคำ อ่านออกเสียง และเครื่องมือแปลอัตโนมัติ
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const value = useMemo<Ctx>(
    () => ({ lang, setLang, t: (s: string) => DICTS[lang][s] ?? s }),
    [lang],
  );
  return <LangCtx.Provider value={value}>{children}</LangCtx.Provider>;
}

export const useLang = () => useContext(LangCtx);

/** ชื่อสินค้า/หมวดตามภาษาที่เลือก — ไม่มีอังกฤษก็ถอยไปใช้ไทย
 *
 *  ของจริงมีชื่ออังกฤษแค่ 62% ของสินค้าที่ขึ้นเว็บ (ฝ่ายสินค้ายังแปลไม่ครบ)
 *  ปล่อยว่างจะเห็นการ์ดไม่มีชื่อ ซึ่งแย่กว่าเห็นชื่อไทยปนมา
 */
export function localName(lang: Lang, th: string, en?: string | null): string {
  return lang === "en" && en ? en : th;
}
