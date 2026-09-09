import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, apiGet, errorMessage } from "./api";
import { useAuth } from "./auth";
import type { Cart } from "./types";

export type AddOpts = { qty?: number; supply_mode?: string | null; plant_code?: string | null; note?: string | null };

type CartState = {
  cart: Cart | null;
  loading: boolean;
  error: string | null;
  count: number;
  refresh: () => Promise<void>;
  add: (matnr: string, opts?: AddOpts) => Promise<Cart>;
  update: (itemId: string, patch: { qty?: number; supply_mode?: string; plant_code?: string | null; note?: string }) => Promise<Cart>;
  remove: (itemId: string) => Promise<Cart>;
  ack: (itemId: string) => Promise<Cart>;
  select: (itemIds: string[] | null, selected: boolean) => Promise<Cart>;
  setShipTo: (postcode: string | null) => Promise<Cart>;
  setCart: (c: Cart | null) => void;
};

const Ctx = createContext<CartState | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isStaff = auth.role === "sales" || auth.role === "manager" || auth.role === "admin";

  const refresh = useCallback(async () => {
    if (!auth.ready) return;
    if (isStaff) {
      setCart(null); // พนักงานใช้ตะกร้าผ่านโหมดเซลล์ (/sales/carts)
      return;
    }
    setLoading(true);
    try {
      setCart(await apiGet<Cart>("/cart"));
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [auth.ready, isStaff, auth.user?.id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const value = useMemo<CartState>(
    () => ({
      cart,
      loading,
      error,
      count: cart ? cart.all_count : 0, // ป้ายบนหัวเว็บนับของทั้งตะกร้า (cart.count = เฉพาะที่ติ๊ก)
      refresh,
      setCart,
      add: async (matnr, opts = {}) => {
        const c = await api<Cart>("POST", "/cart/items", { matnr, qty: opts.qty ?? 1, supply_mode: opts.supply_mode ?? null, plant_code: opts.plant_code ?? null, note: opts.note ?? null });
        setCart(c);
        return c;
      },
      update: async (itemId, patch) => {
        const c = await api<Cart>("PATCH", `/cart/items/${itemId}`, patch);
        setCart(c);
        return c;
      },
      remove: async (itemId) => {
        const c = await api<Cart>("DELETE", `/cart/items/${itemId}`);
        setCart(c);
        return c;
      },
      ack: async (itemId) => {
        const c = await api<Cart>("POST", `/cart/items/${itemId}/ack`, {});
        setCart(c);
        return c;
      },
      // ปลายทางคร่าวๆ (จังหวัดที่เลือกบน nav) — ส่งไปให้หลังบ้านคิดค่าส่งจริง
      setShipTo: async (postcode) => {
        const c = await api<Cart>("POST", "/cart/shipto", { postcode });
        setCart(c);
        return c;
      },
      // ติ๊ก/เอาติ๊กออก — itemIds = null คือทั้งตะกร้า
      select: async (itemIds, selected) => {
        const c = await api<Cart>("POST", "/cart/select", { item_ids: itemIds, selected });
        setCart(c);
        return c;
      },
    }),
    [cart, loading, error, refresh],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCart(): CartState {
  const c = useContext(Ctx);
  if (!c) throw new Error("useCart must be used inside CartProvider");
  return c;
}

export const SUPPLY_LABEL: Record<string, string> = { takeaway: "ยกกลับ", ship: "จัดส่ง", install: "ส่ง + ติดตั้ง", pickup: "รับที่สาขา" };
