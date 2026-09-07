export type Role = "guest" | "customer" | "sales" | "manager" | "admin";

export type User = {
  id: string;
  role: Exclude<Role, "guest">;
  name: string;
  phone: string | null;
  email: string | null;
  sap_customer_no: string | null;
  staff_code: string | null;
  branch_id: string | null;
  tier: string | null;
  is_guest: boolean;
  default_address: string | null;
  default_postcode: string | null;
};

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
};

// ---------- catalog ----------
export type Category = {
  id: string;
  name_th: string;
  name_en?: string | null;
  room?: string | null;
  icon?: string | null;
  children: Category[];
};

export type Brand = { id: string; name: string };

export type Plant = { plant_code: string; name: string; type: "store" | "warehouse"; address: string | null };

export type StockSummary = {
  available_total: number;
  store_available: number;
  warehouse_available: number;
  fetched_at: string | null;
};

export type MaterialCard = {
  matnr: string;
  sku: string;
  name_th: string;
  name_en: string | null;
  variant: string | null;
  spec: string | null;
  category_id: string | null;
  category_name: string | null;
  brand_id: string | null;
  brand_name: string | null;
  room: string | null;
  image_url: string | null;
  price: string;
  price_tier: string;
  standard_price: string;
  member_price: string | null;
  compare_at_price: string | null;
  discount_percent: number | null;
  requires_install: boolean;
  is_takeaway_ok: boolean;
  is_new: boolean;
  tags: string[];
  stock: StockSummary | null;
};

export type MaterialDetail = MaterialCard & {
  barcode: string | null;
  description: string | null;
  volume_m3: string | null;
  weight_kg: string | null;
  synced_at: string;
};

export type SearchOut = { items: MaterialCard[]; total: number; q: string | null; category: string | null };

export type StockRow = {
  plant_code: string;
  plant_name: string;
  plant_type: "store" | "warehouse";
  on_hand: number;
  reserved: number;
  available: number;
  atp_date: string | null;
  note: string | null;
};

export type StockOut = {
  matnr: string;
  source: "sap" | "cache";
  stale: boolean;
  fetched_at: string;
  stale_minutes: number;
  available: boolean;
  earliest_atp: string | null;
  rows: StockRow[];
  error: string | null;
};

// ---------- cart ----------
export type SupplyMode = "takeaway" | "ship" | "install" | "pickup";

export type CartItem = {
  id: string;
  matnr: string;
  sku: string;
  name: string;
  variant: string | null;
  spec: string | null;
  image_url: string | null;
  category_id: string | null;
  qty: number;
  unit_price: string;
  price_tier: string;
  line_total: string;
  added_by: "customer" | "sales";
  added_by_name: string | null;
  added_by_code: string | null;
  added_at: string;
  pending_ack: boolean;
  supply_mode: SupplyMode;
  plant_code: string | null;
  atp_date: string | null;
  requires_install: boolean;
  note: string | null;
};

export type CartPerson = {
  id: string;
  name: string;
  tier: string | null;
  sap_customer_no: string | null;
  staff_code: string | null;
  phone: string | null;
  branch_id: string | null;
};

export type Cart = {
  id: string;
  no: string;
  label: string | null;
  status: "open" | "merged" | "converted" | "abandoned";
  customer: CartPerson | null;
  owner_sales: CartPerson | null;
  is_guest: boolean;
  items: CartItem[];
  count: number;
  subtotal: string;
  pending_count: number;
  expires_at: string | null;
  updated_at: string;
};

// ---------- home content ----------
export type NavLink = { label: string; href: string };
export type HomeContent = {
  hero_slides: { id: string; tag: string; title: string; note: string; cta: string; href: string; art: string }[];
  promo_cards: { tag: string; title: string; note: string; href: string }[];
  services: { icon: string; label: string }[];
  category_tiles: { label: string; category: string }[];
  new_collections: NavLink[];
  room_rows: { label: string; room: string; items: { label: string; category: string }[] }[];
  rooms: { label: string; room: string }[];
  main_nav: { label: string; items: NavLink[] }[];
  footer_promos: { head: string; body: string; cta: string; href: string }[];
  footer_cols: { head: string; items: string[] }[];
  payments: string[];
  legal_links: string[];
  support_line: string;
  free_shipping_note: string;
  categories: Category[];
  new_products: MaterialCard[];
  deals: MaterialCard[];
  bestsellers: MaterialCard[];
  brands: Brand[];
};
