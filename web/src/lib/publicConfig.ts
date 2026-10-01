import { useEffect, useState } from "react";
import { apiGet } from "./api";

/** ค่าที่หลังบ้านบอกหน้าเว็บก่อนเข้าสู่ระบบ
 *
 *  อ่านตอนรันไทม์ ไม่ใช่ฝังตอน build — จะเปิด/ปิดช่วงทดสอบก็แก้ env ฝั่งหลังบ้านแล้วรีสตาร์ท
 *  ไม่ต้อง build เว็บใหม่ และไม่มีทางที่หน้าเว็บกับหลังบ้านจะตั้งค่าไม่ตรงกัน
 */
export type PublicConfig = {
  invite_only: boolean;
  /** false = ระบบส่ง OTP ไม่ได้ (ยังไม่ได้ต่อ SMS) — ต้องซ่อนปุ่ม OTP ไม่งั้นกดแล้วตัน */
  otp_enabled: boolean;
  coming_soon_title: string;
  coming_soon_text: string;
};

// ยิงครั้งเดียวต่อการเปิดเว็บ แล้วแชร์ผลให้ทุกหน้า (หลายหน้าถามพร้อมกันตอนโหลดแรก)
let cached: Promise<PublicConfig> | null = null;

export function loadPublicConfig(): Promise<PublicConfig> {
  if (!cached) {
    cached = apiGet<PublicConfig>("/public-config").catch(() => ({
      // หลังบ้านล่ม/ตอบไม่ได้ = ไม่ควรเผลอเปิดประตูทิ้งไว้ ปิดไว้ก่อนปลอดภัยกว่า
      // (ถึงเปิดหน้าฟอร์มได้ หลังบ้านก็ยังกันการสมัครอยู่ดี ตรงนี้แค่ให้หน้าจอไม่หลอกตา)
      invite_only: true,
      otp_enabled: false,
      coming_soon_title: "เร็ว ๆ นี้",
      coming_soon_text: "เรากำลังเตรียมร้านค้าออนไลน์ให้พร้อมที่สุด อีกไม่นานเจอกันแน่นอน",
    }));
  }
  return cached;
}

/** null = ยังไม่รู้ (กำลังโหลด) — หน้าจอควรยังไม่ตัดสินใจอะไรจนกว่าจะได้ค่า */
export function usePublicConfig(): PublicConfig | null {
  const [cfg, setCfg] = useState<PublicConfig | null>(null);
  useEffect(() => {
    let alive = true;
    loadPublicConfig().then((c) => alive && setCfg(c));
    return () => { alive = false; };
  }, []);
  return cfg;
}
