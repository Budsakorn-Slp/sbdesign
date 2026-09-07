import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { apiGet } from "./api";
import type { HomeContent, Plant } from "./types";

type Prefs = {
  content: HomeContent | null;
  plants: Plant[];
  plant: Plant | null;
  setPlantCode: (code: string | null) => void;
  postcode: string;
  setPostcode: (pc: string) => void;
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

export function ContentProvider({ children }: { children: ReactNode }) {
  const [content, setContent] = useState<HomeContent | null>(null);
  const [plants, setPlants] = useState<Plant[]>([]);
  const [plantCode, setPlantCodeState] = useState<string | null>(readLS("sb_plant"));
  const [postcode, setPostcodeState] = useState<string>(readLS("sb_postcode") || "");
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

  const value = useMemo<Prefs>(
    () => ({
      content,
      plants,
      plant: plants.find((p) => p.plant_code === plantCode) || null,
      setPlantCode,
      postcode,
      setPostcode,
      reload: () => setTick((t) => t + 1),
    }),
    [content, plants, plantCode, postcode, setPlantCode, setPostcode],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useContent(): Prefs {
  const c = useContext(Ctx);
  if (!c) throw new Error("useContent must be used inside ContentProvider");
  return c;
}
