import { useCallback, useEffect, useState } from "react";
import { apiGet } from "./api";
import { useAuth } from "./auth";
import type { PendingPayment } from "./types";

/** รายการรอชำระของผู้ใช้ที่ล็อกอินอยู่ — ใช้ร่วมกันระหว่างกระดิ่งกับแท็บในหน้าบัญชี
 *
 *  ดึงใหม่ตอนเปลี่ยนหน้าไม่ได้ เพราะกระดิ่งอยู่บนหัวเว็บตลอดเวลา จึงรีเฟรชเป็นรอบ
 *  ห่างๆ (60 วิ) พอให้เลขไม่ค้างนาน โดยไม่ยิงถี่จนเปลืองเปล่า
 */
export function usePendingPayments(pollMs = 60_000) {
  const auth = useAuth();
  const [rows, setRows] = useState<PendingPayment[]>([]);

  const load = useCallback(() => {
    if (!auth.user || auth.user.role !== "customer") { setRows([]); return; }
    apiGet<PendingPayment[]>("/me/pending-payments").then(setRows).catch(() => setRows([]));
  }, [auth.user]);

  useEffect(() => {
    load();
    if (!auth.user) return;
    const id = window.setInterval(load, pollMs);
    return () => window.clearInterval(id);
  }, [load, auth.user, pollMs]);

  return { rows, count: rows.length, reload: load };
}

/** นับถอยหลังเป็นข้อความอ่านง่าย — หมดเวลาแล้วบอกตรงๆ ไม่โชว์เลขติดลบ */
export function timeLeftText(seconds: number | null): string {
  if (seconds === null) return "ยังไม่ได้สร้างรายการชำระ";
  if (seconds <= 0) return "หมดเวลาแล้ว";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h >= 1) return `เหลือ ${h} ชม. ${m} นาที`;
  return `เหลือ ${m} นาที`;
}
