import { apiGet } from "./api";
import type { District, PostcodeHit, Province, Subdistrict } from "./types";

/** ตัวช่วยเรียก /geo/* พร้อมแคชในหน่วยความจำ
 *
 * ชุดที่อยู่ไทยแทบไม่เปลี่ยน (sync วันละครั้ง) และหน้าเดียวอาจถามซ้ำหลายรอบ
 * — ลูกค้าเปลี่ยนจังหวัดกลับไปกลับมา หรือมีทั้ง picker บน nav และในหน้า checkout
 * เลยแคชด้วย Promise ไว้เลย ยิงพร้อมกันสองที่ก็เหลือ request เดียว
 */
const cache = new Map<string, Promise<unknown>>();

function cached<T>(key: string, run: () => Promise<T>): Promise<T> {
  let p = cache.get(key) as Promise<T> | undefined;
  if (!p) {
    p = run().catch((e) => {
      cache.delete(key); // พังแล้วอย่าจำไว้ ให้ลองใหม่ได้
      throw e;
    });
    cache.set(key, p);
  }
  return p;
}

export const getProvinces = () => cached("provinces", () => apiGet<Province[]>("/geo/provinces"));
export const getDistricts = (provinceId: number) =>
  cached(`d:${provinceId}`, () => apiGet<District[]>(`/geo/districts?province_id=${provinceId}`));
export const getSubdistricts = (districtId: number) =>
  cached(`s:${districtId}`, () => apiGet<Subdistrict[]>(`/geo/subdistricts?district_id=${districtId}`));

/** รหัสไปรษณีย์ 5 หลัก -> ตำบลที่เป็นไปได้ (รหัสเดียวคร่อมหลายอำเภอได้) · ไม่ครบ 5 หลัก = [] */
export function lookupPostcode(zipcode: string): Promise<PostcodeHit[]> {
  const pc = zipcode.trim();
  if (pc.length !== 5 || !/^\d{5}$/.test(pc)) return Promise.resolve([]);
  return cached(`p:${pc}`, () => apiGet<PostcodeHit[]>(`/geo/postcode/${pc}`).catch(() => []));
}

/** พิมพ์ไปหาไป — รับได้ทั้งรหัสบางส่วน ("10") และชื่อตำบล/อำเภอ/จังหวัด
 *
 * แคชด้วยคำค้น เพราะคนพิมพ์แล้วลบแล้วพิมพ์ซ้ำบ่อย และชุดข้อมูลนิ่งทั้งวัน
 */
export function searchGeo(q: string, limit = 20): Promise<PostcodeHit[]> {
  const term = q.trim();
  if (!term) return Promise.resolve([]);
  return cached(`q:${limit}:${term}`, () =>
    apiGet<PostcodeHit[]>(`/geo/search?q=${encodeURIComponent(term)}&limit=${limit}`).catch(() => []),
  );
}

export const areaLabel =(areaId: number | null | undefined) =>
  areaId === 1 ? "กทม. และปริมณฑล" : areaId === 2 ? "ต่างจังหวัด" : "";
