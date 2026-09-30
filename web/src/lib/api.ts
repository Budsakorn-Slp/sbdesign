export const API_BASE: string = import.meta.env.VITE_API_BASE || "/api";

const STORAGE_KEY = "sb_auth";

export type StoredAuth = {
  access_token: string;
  refresh_token: string;
};

/** ใครล็อกอินอยู่ — แยกรายแท็บ ไม่ใช่รายเบราว์เซอร์
 *
 *  ของเดิมเก็บไว้ที่ localStorage อย่างเดียว ซึ่งทุกแท็บของโดเมนเดียวกันใช้ร่วมกัน
 *  เปิดสองแท็บแล้วล็อกอินคนละคน (พนักงานแท็บหนึ่ง ลูกค้าอีกแท็บหนึ่ง) คนที่ล็อกอิน
 *  ทีหลังจะทับของเดิม พอกด F5 ทั้งสองแท็บก็กลายเป็นคนเดียวกัน
 *
 *  วิธีแก้:
 *    sessionStorage  = ตัวจริงของแท็บนี้ ไม่ข้ามแท็บ
 *    localStorage    = ตัวสำรองไว้ให้แท็บที่เปิดใหม่ (จะได้ไม่ต้องล็อกอินซ้ำทุกครั้ง)
 *  แท็บที่เปิดอยู่แล้วจะยึดของตัวเองเสมอ ไม่โดนแท็บอื่นเปลี่ยนกลางคัน
 */
function read(store: Storage): StoredAuth | null {
  try {
    const raw = store.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredAuth) : null;
  } catch {
    return null;
  }
}

export function loadAuth(): StoredAuth | null {
  const mine = read(sessionStorage);
  if (mine) return mine;
  // แท็บเพิ่งเปิด — หยิบของล่าสุดมาใช้ แล้วปักไว้เป็นของแท็บนี้
  const shared = read(localStorage);
  if (shared) {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(shared));
    } catch {
      /* storage ถูกปิด — ใช้ต่อได้ แค่ไม่จำข้ามการรีเฟรช */
    }
  }
  return shared;
}

export function saveAuth(a: StoredAuth | null): void {
  try {
    if (a) {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(a));
      localStorage.setItem(STORAGE_KEY, JSON.stringify(a));
      return;
    }
    // ออกจากระบบ: เคลียร์ของแท็บนี้เสมอ ส่วนตัวสำรองลบเฉพาะตอนที่เป็นคนเดียวกัน
    // ไม่งั้นลูกค้ากดออกจากระบบแล้วแท็บพนักงานที่เปิดค้างอยู่จะหลุดตามไปด้วยตอนรีเฟรช
    const mine = read(sessionStorage);
    const shared = read(localStorage);
    sessionStorage.removeItem(STORAGE_KEY);
    if (!mine || !shared || shared.access_token === mine.access_token) localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage อาจถูกปิด — ใช้งานต่อได้แบบไม่จำ session */
  }
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

type Method = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  const cur = loadAuth();
  if (!cur) return false;
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: cur.refresh_token }),
        });
        if (!res.ok) {
          saveAuth(null);
          return false;
        }
        const data = (await res.json()) as StoredAuth;
        saveAuth({ access_token: data.access_token, refresh_token: data.refresh_token });
        return true;
      } catch {
        return false;
      } finally {
        refreshing = null;
      }
    })();
  }
  return refreshing;
}

export async function api<T>(method: Method, path: string, body?: unknown, retry = true): Promise<T> {
  const auth = loadAuth();
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) headers["Authorization"] = `Bearer ${auth.access_token}`;
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401 && auth && retry && !path.startsWith("/auth/")) {
    if (await tryRefresh()) return api<T>(method, path, body, false);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = data && typeof data === "object" && "detail" in data ? (data as { detail: unknown }).detail : data;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

export const apiGet = <T>(path: string) => api<T>("GET", path);
export const apiPost = <T>(path: string, body?: unknown) => api<T>("POST", path, body ?? {});
export const apiPatch = <T>(path: string, body?: unknown) => api<T>("PATCH", path, body ?? {});
export const apiDelete = <T>(path: string, body?: unknown) => api<T>("DELETE", path, body);

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (typeof e.detail === "string") return e.detail;
    if (Array.isArray(e.detail)) return e.detail.map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : String(d))).join(", ");
    // detail แบบ object: หลังบ้านส่งรายละเอียดเพิ่ม (เช่น มูลค่าโค้ดที่ชนกัน) มาพร้อมข้อความ
    if (e.detail && typeof e.detail === "object" && "message" in e.detail) return String((e.detail as { message: unknown }).message);
    return e.message;
  }
  if (e instanceof Error) return e.message;
  return String(e);
}
