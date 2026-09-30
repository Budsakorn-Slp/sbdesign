import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { apiGet, apiPost, loadAuth, saveAuth } from "./api";
import type { Role, TokenPair, User } from "./types";
import { resetWishlist } from "./wishlist";

type AuthState = {
  user: User | null;
  role: Role;
  ready: boolean;
  loginOpen: boolean;
  /** เปิดกล่องเข้าสู่ระบบทับหน้าที่กำลังทำอยู่ (หน้า /login ยังใช้ได้สำหรับลิงก์ตรง) */
  openLogin: () => void;
  closeLogin: () => void;
  login: (identifier: string, password: string, accountType: "customer" | "staff") => Promise<User>;
  register: (phone: string, password: string, name: string, email?: string) => Promise<User>;
  otpRequest: (phone: string) => Promise<{ debug_code?: string }>;
  otpVerify: (phone: string, code: string, name?: string) => Promise<User>;
  /** รับ token ที่ได้จาก endpoint อื่น (เช่น ตั้งรหัสผ่านใหม่) มาเข้าสู่ระบบเลย */
  adopt: (t: TokenPair) => User;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
};

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [loginOpen, setLoginOpen] = useState(false);

  const refreshMe = useCallback(async () => {
    if (!loadAuth()) {
      setUser(null);
      return;
    }
    try {
      setUser(await apiGet<User>("/me"));
    } catch {
      saveAuth(null);
      setUser(null);
    }
  }, []);

  useEffect(() => {
    refreshMe().finally(() => setReady(true));
  }, [refreshMe]);

  const accept = useCallback((t: TokenPair) => {
    resetWishlist(); // สลับผู้ใช้ ต้องล้างหัวใจของคนก่อน แล้วให้โหลดใหม่ตามบัญชีนี้
    saveAuth({ access_token: t.access_token, refresh_token: t.refresh_token });
    setUser(t.user);
    window.dispatchEvent(new CustomEvent("sb:auth-changed"));
    return t.user;
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      role: user ? user.role : "guest",
      ready,
      loginOpen,
      openLogin: () => setLoginOpen(true),
      closeLogin: () => setLoginOpen(false),
      login: async (identifier, password, accountType) =>
        accept(await apiPost<TokenPair>("/auth/login", { identifier, password, account_type: accountType })),
      register: async (phone, password, name, email) =>
        accept(await apiPost<TokenPair>("/auth/register", { phone, password, name, email: email || null })),
      otpRequest: (phone) => apiPost<{ debug_code?: string }>("/auth/otp/request", { phone }),
      adopt: accept,
      otpVerify: async (phone, code, name) => accept(await apiPost<TokenPair>("/auth/otp/verify", { phone, code, name: name || null })),
      logout: async () => {
        const a = loadAuth();
        if (a) {
          try {
            await apiPost("/auth/logout", { refresh_token: a.refresh_token });
          } catch {
            /* ignore */
          }
        }
        saveAuth(null);
        setUser(null);
        resetWishlist();
        window.dispatchEvent(new CustomEvent("sb:auth-changed"));
      },
      refreshMe,
    }),
    [user, ready, loginOpen, accept, refreshMe],
  );

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

// ต้องตรงกับ DEFAULT_PASSWORD ใน backend/app/seed.py — ปุ่มกรอกอัตโนมัติกับข้อความใต้ปุ่มอ่านจากตัวนี้ตัวเดียว
export const DEMO_PASSWORD = "1122";

export const DEMO_ACCOUNTS = [
  { type: "customer" as const, title: "ลูกค้า — ณภัทร", id: "094-916-4600" },
  { type: "customer" as const, title: "ลูกค้า — วีระ", id: "081-222-3333" },
  { type: "staff" as const, title: "พนักงานขาย — สมชาย ก.", id: "SA-104" },
  { type: "staff" as const, title: "ผู้จัดการสาขา — มานะ", id: "MG-001" },
  { type: "staff" as const, title: "แอดมินระบบ", id: "ADM-001" },
].map((a) => ({ ...a, sub: `${a.id} · รหัส ${DEMO_PASSWORD}` }));

export const ROLE_PERMS: Record<Role, { ok: boolean; label: string }[]> = {
  guest: [
    { ok: true, label: "ดู / แก้ไขสินค้าในตะกร้าได้" },
    { ok: false, label: "ชำระเงินไม่ได้ — ต้องเข้าสู่ระบบหรือลงทะเบียนก่อน" },
    { ok: false, label: "ไม่เห็นราคาสมาชิกและโปรเฉพาะสมาชิก" },
  ],
  customer: [
    { ok: true, label: "แก้ไขตะกร้า + ชำระเงินได้เอง" },
    { ok: true, label: "เห็นราคาสมาชิกและโปรที่ใช้ได้" },
    { ok: true, label: "ลบสินค้าที่พนักงานเพิ่มให้ได้ทุกเมื่อ" },
    { ok: false, label: "ไม่เห็นต้นทุน สต็อกข้ามสาขา และเครื่องมือของพนักงาน" },
  ],
  sales: [
    { ok: true, label: "เพิ่ม / แก้ไขสินค้าในตะกร้าลูกค้าได้ ถือหลายตะกร้าพร้อมกัน" },
    { ok: true, label: "เช็คสต็อกข้ามสาขา · โปรโมชั่น · คิวจัดส่ง" },
    { ok: true, label: "Save Preso และออกใบเสนอราคา (Quotation) · ส่วนลด ≤ 3%" },
    { ok: false, label: "รับเงินเองไม่ได้ — ลูกค้าจ่ายผ่าน QR / ลิงก์ / แคชเชียร์" },
  ],
  manager: [
    { ok: true, label: "ทุกอย่างของพนักงานขาย" },
    { ok: true, label: "อนุมัติส่วนลดเกินโควตา 3%" },
    { ok: true, label: "ดูรายงานยอดขายทีม" },
  ],
  admin: [
    { ok: true, label: "จัดการผู้ใช้ · ตั้งค่าระบบ" },
    { ok: true, label: "ดู audit log · รายการ sync SAP ที่ล้มเหลว" },
  ],
};
