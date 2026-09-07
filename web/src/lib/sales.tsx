import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, apiGet } from "./api";
import { useAuth } from "./auth";
import type { Cart, SearchOut } from "./types";

export type SalesCartSummary = {
  id: string;
  no: string;
  label: string | null;
  customer_name: string | null;
  customer_tier: string | null;
  sap_customer_no: string | null;
  count: number;
  subtotal: string;
  pending_count: number;
  expires_at: string | null;
  updated_at: string;
};

export type CustomerHit = {
  id: string | null;
  name: string;
  tier: string | null;
  sap_customer_no: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  postcode: string | null;
  online_cart_count: number;
  source: "local" | "sap";
};

type SalesState = {
  enabled: boolean;
  sessions: SalesCartSummary[];
  activeId: string | null;
  active: Cart | null;
  loading: boolean;
  setActiveId: (id: string) => void;
  reload: () => Promise<void>;
  reloadActive: () => Promise<void>;
  openCart: (label?: string) => Promise<Cart>;
  closeCart: (id: string) => Promise<void>;
  attach: (customerKey: string) => Promise<Cart>;
  detach: () => Promise<Cart>;
  addItem: (matnr: string, qty: number, supply_mode?: string | null, plant_code?: string | null) => Promise<Cart>;
  updateItem: (itemId: string, patch: { qty?: number; supply_mode?: string; plant_code?: string | null; note?: string }) => Promise<Cart>;
  removeItem: (itemId: string) => Promise<Cart>;
  searchCustomers: (q: string) => Promise<CustomerHit[]>;
  searchMaterials: (q: string) => Promise<SearchOut>;
  setActive: (c: Cart | null) => void;
};

const Ctx = createContext<SalesState | null>(null);

export function SalesProvider({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const enabled = auth.role === "sales" || auth.role === "manager";
  const [sessions, setSessions] = useState<SalesCartSummary[]>([]);
  const [activeId, setActiveIdState] = useState<string | null>(null);
  const [active, setActive] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(false);

  const reload = useCallback(async () => {
    if (!enabled) {
      setSessions([]);
      setActive(null);
      setActiveIdState(null);
      return;
    }
    setLoading(true);
    try {
      const list = await apiGet<SalesCartSummary[]>("/sales/carts");
      setSessions(list);
      setActiveIdState((cur) => (cur && list.some((s) => s.id === cur) ? cur : list[0]?.id || null));
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  const reloadActive = useCallback(async () => {
    if (!enabled || !activeId) {
      setActive(null);
      return;
    }
    try {
      setActive(await apiGet<Cart>(`/sales/carts/${activeId}`));
    } catch {
      setActive(null);
      await reload();
    }
  }, [enabled, activeId, reload]);

  useEffect(() => {
    reload();
  }, [reload, auth.user?.id]);

  useEffect(() => {
    reloadActive();
  }, [reloadActive]);

  const applyCart = useCallback(
    (c: Cart) => {
      setActive(c);
      setSessions((prev) =>
        prev.map((s) =>
          s.id === c.id
            ? { ...s, label: c.label, customer_name: c.customer?.name || null, customer_tier: c.customer?.tier || null, sap_customer_no: c.customer?.sap_customer_no || null, count: c.count, subtotal: c.subtotal, pending_count: c.pending_count, updated_at: c.updated_at, expires_at: c.expires_at }
            : s,
        ),
      );
      return c;
    },
    [],
  );

  const value = useMemo<SalesState>(
    () => ({
      enabled,
      sessions,
      activeId,
      active,
      loading,
      setActiveId: (id) => setActiveIdState(id),
      reload,
      reloadActive,
      setActive,
      openCart: async (label) => {
        const c = await api<Cart>("POST", "/sales/carts", { label: label || null });
        await reload();
        setActiveIdState(c.id);
        return c;
      },
      closeCart: async (id) => {
        await api("DELETE", `/sales/carts/${id}`);
        if (activeId === id) setActiveIdState(null);
        await reload();
      },
      attach: async (customerKey) => applyCart(await api<Cart>("POST", `/sales/carts/${activeId}/attach-customer`, { customer_key: customerKey })),
      detach: async () => applyCart(await api<Cart>("DELETE", `/sales/carts/${activeId}/attach-customer`)),
      addItem: async (matnr, qty, supply_mode = null, plant_code = null) => applyCart(await api<Cart>("POST", `/sales/carts/${activeId}/items`, { matnr, qty, supply_mode, plant_code })),
      updateItem: async (itemId, patch) => applyCart(await api<Cart>("PATCH", `/sales/carts/${activeId}/items/${itemId}`, patch)),
      removeItem: async (itemId) => applyCart(await api<Cart>("DELETE", `/sales/carts/${activeId}/items/${itemId}`)),
      searchCustomers: (q) => apiGet<CustomerHit[]>(`/customers/search?q=${encodeURIComponent(q)}`),
      searchMaterials: (q) => apiGet<SearchOut>(`/materials/search?q=${encodeURIComponent(q)}&limit=12`),
    }),
    [enabled, sessions, activeId, active, loading, reload, reloadActive, applyCart],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSales(): SalesState {
  const c = useContext(Ctx);
  if (!c) throw new Error("useSales must be used inside SalesProvider");
  return c;
}
