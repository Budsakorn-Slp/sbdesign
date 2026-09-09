import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { apiGet } from "./api";
import type { HomeContent, Plant } from "./types";

/** จังหวัดที่ลูกค้าเลือกไว้คร่าวๆ ก่อนกรอกที่อยู่เต็ม
 *
 * ค่าส่งของเราขึ้นกับเขต (1 = กทม.+ปริมณฑล · 2 = ต่างจังหวัด) ซึ่งรู้ได้ตั้งแต่รู้จังหวัด
 * exact = true คือได้มาจากรหัสไปรษณีย์จริงที่ลูกค้ากรอก ไม่ใช่รหัสตัวแทนของจังหวัด
 */
export type ShipTo = { province_id: number; name_th: string; area_id: number | null; postcode: string; exact: boolean };

type Prefs = {
  content: HomeContent | null;
  plants: Plant[];
  plant: Plant | null;
  setPlantCode: (code: string | null) => void;
  postcode: string;
  setPostcode: (pc: string) => void;
  shipTo: ShipTo | null;
  setShipTo: (s: ShipTo | null) => void;
  reload: () => void;
};

const Ctx = createContext<Prefs | null>(null);

function readLS(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function writeLS(key: string, val: string | null) {
  try {
    if (val === null) localStorage.removeItem(key);
    else localStorage.setItem(key, val);
  } catch {
    /* ignore */
  }
}

function readShipTo(): ShipTo | null {
  const raw = readLS("sb_shipto");
  if (!raw) return null;
  try {
    const s = JSON.parse(raw) as ShipTo;
    return s && typeof s.province_id === "number" && s.name_th ? s : null;
  } catch {
    return null;
  }
}

export function ContentProvider({ children }: { children: ReactNode }) {
  const [content, setContent] = useState<HomeContent | null>(null);
  const [plants, setPlants] = useState<Plant[]>([]);
  const [plantCode, setPlantCodeState] = useState<string | null>(readLS("sb_plant"));
  const [postcode, setPostcodeState] = useState<string>(readLS("sb_postcode") || "");
  const [shipTo, setShipToState] = useState<ShipTo | null>(readShipTo);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    apiGet<HomeContent>("/home").then(setContent).catch(() => setContent(null));
    apiGet<Plant[]>("/plants").then(setPlants).catch(() => setPlants([]));
  }, [tick]);

  // ราคาสมาชิกใน /home ขึ้นกับ user → โหลดใหม่เมื่อ auth เปลี่ยน
  useEffect(() => {
    const h = () => setTick((t) => t + 1);
    window.addEventListener("sb:auth-changed", h);
    return () => window.removeEventListener("sb:auth-changed", h);
  }, []);

  const setPlantCode = useCallback((code: string | null) => {
    setPlantCodeState(code);
    writeLS("sb_plant", code);
  }, []);
  const setPostcode = useCallback((pc: string) => {
    setPostcodeState(pc);
    writeLS("sb_postcode", pc || null);
  }, []);
  // เลือกจังหวัด = ได้รหัสไปรษณีย์ไปด้วยเสมอ (ตัวแทนจังหวัด หรือรหัสจริงถ้ากรอกเอง)
  // ค่าส่งจะได้คิดได้ทันทีโดยไม่ต้องรอที่อยู่เต็ม
  const setShipTo = useCallback((s: ShipTo | null) => {
    setShipToState(s);
    writeLS("sb_shipto", s ? JSON.stringify(s) : null);
    setPostcodeState(s?.postcode || "");
    writeLS("sb_postcode", s?.postcode || null);
  }, []);

  const value = useMemo<Prefs>(
    () => ({
      content,
      plants,
      plant: plants.find((p) => p.plant_code === plantCode) || null,
      setPlantCode,
      postcode,
      setPostcode,
      shipTo,
      setShipTo,
      reload: () => setTick((t) => t + 1),
    }),
    [content, plants, plantCode, postcode, shipTo, setPlantCode, setPostcode, setShipTo],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useContent(): Prefs {
  const c = useContext(Ctx);
  if (!c) throw new Error("useContent must be used inside ContentProvider");
  return c;
}
