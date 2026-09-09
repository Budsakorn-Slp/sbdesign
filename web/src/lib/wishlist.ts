/** รายการโปรดที่ใช้ร่วมกันทั้งหน้า
 *
 * การ์ดสินค้ามีปุ่มหัวใจทุกใบ ถ้าต่างคนต่างยิง /me/wishlist หน้าเดียวก็ยิงเป็นสิบรอบ
 * เลยเก็บเป็นชุดเดียวไว้ตรงนี้ โหลดครั้งแรกครั้งเดียว แล้วให้ทุกใบ subscribe เอา
 */
import { useEffect, useState } from "react";
import { apiGet, apiPost } from "./api";

let items = new Set<string>();
let loaded = false;
let inflight: Promise<void> | null = null;
const subs = new Set<(s: Set<string>) => void>();

const publish = () => {
  items = new Set(items); // ก็อปใหม่ให้ React เห็นว่าเปลี่ยน
  subs.forEach((fn) => fn(items));
};

function load(): Promise<void> {
  if (loaded) return Promise.resolve();
  if (!inflight) {
    inflight = apiGet<{ matnr: string }[]>("/me/wishlist")
      .then((ws) => {
        items = new Set(ws.map((w) => w.matnr));
        loaded = true;
        publish();
      })
      .catch(() => {})
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

/** ล้างตอนออกจากระบบ/สลับผู้ใช้ ไม่งั้นหัวใจของคนก่อนหน้าค้างอยู่ */
export function resetWishlist() {
  items = new Set();
  loaded = false;
  publish();
}

export function useWishlist(enabled: boolean) {
  const [set, setSet] = useState(items);

  useEffect(() => {
    subs.add(setSet);
    if (enabled) void load();
    return () => {
      subs.delete(setSet);
    };
  }, [enabled]);

  return {
    has: (matnr: string) => set.has(matnr),
    toggle: async (matnr: string) => {
      // สลับให้เห็นผลทันที แล้วค่อยยืนยันกับหลังบ้าน
      if (items.has(matnr)) items.delete(matnr);
      else items.add(matnr);
      publish();
      const r = await apiPost<{ in_wishlist: boolean }>(`/me/wishlist/${matnr}`);
      if (r.in_wishlist) items.add(matnr);
      else items.delete(matnr);
      publish();
      return r.in_wishlist;
    },
  };
}
