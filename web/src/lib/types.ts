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
  email: string | null;
  default_address: string | null;
  default_postcode: string | null;
};

export type DiscountLine = {
  id: string;
  kind: "promotion" | "staff_manual" | "member_price";
  code: string | null;
  title: string | null;
  amount: string;
  status: "applied" | "pending_approval" | "rejected" | "removed";
  percent: string | null;
};

export type Totals = {
  subtotal: string;
  standard_subtotal: string;
  member_savings: string;
  discount_total: string;
  net_total: string;
  shipping_fee: string;
  install_fee: string;
  shipping_discount: string;
  grand_total: string;
  vat_included: string;
  lines: DiscountLine[];
  warnings: string[];
};

export type CartDelivery = {
  postcode: string | null;
  address: string | null;
  zone: string | null;
  zone_name: string | null;
  shipping_fee: string | null;
  install_fee: string | null;
  slot_id: string | null;
  slot_date: string | null;
  slot_period: "am" | "pm" | null;
  quoted_at: string | null;
};

export type DeliverySlot = {
  id: string;
  date: string;
  period: "am" | "pm";
  zone: string;
  quota: number;
  booked: number;
  remaining: number;
  held_by_this_cart: boolean;
};

export type DeliveryGroup = {
  mode: "takeaway" | "ship" | "install";
  label: string;
  items: { matnr: string; name: string; qty: number; plant_code: string | null }[];
  fee_note: string | null;
};

export type DeliveryQuote = {
  cart_id: string;
  postcode: string;
  zone: string;
  zone_name: string;
  base_fee: string;
  install_fee: string;
  total_fee: string;
  groups: DeliveryGroup[];
  slots: DeliverySlot[];
  held_slot_id: string | null;
};

export type Offer = {
  code: string;
  title: string;
  condition_text: string;
  eligible: boolean;
  amount: string;
  reason: string | null;
  stackable: boolean;
  discount_type: "percent" | "amount" | "gift";
  applied: boolean;
  applied_id: string | null;
};

export type EvaluateOut = {
  cart_id: string;
  customer_name: string | null;
  customer_tier: string | null;
  eligible: Offer[];
  ineligible: Offer[];
  staff_discount_quota_percent: number;
  staff_discount: DiscountLine | null;
  totals: Totals;
};

export type Approval = {
  id: string;
  cart_id: string | null;
  cart_no: string | null;
  customer_name: string | null;
  sales_name: string | null;
  percent: string | null;
  amount: string;
  reason: string | null;
  status: string;
  created_at: string;
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
  totals: Totals | null;
  delivery: CartDelivery | null;
};

// ---------- preso / quotation ----------
export type PresoSummary = {
  id: string;
  preso_no: string;
  status: "draft" | "quoted" | "expired" | "cancelled";
  cart_id: string;
  customer_name: string | null;
  customer_tier: string | null;
  sales_name: string | null;
  item_count: number;
  grand_total: string;
  note: string | null;
  quotation_no: string | null;
  quotation_status: string | null;
  updated_at: string;
  created_at: string;
};

export type Preso = PresoSummary & { snapshot: Record<string, unknown> };

export type QuotationLine = {
  matnr: string;
  sku: string;
  name: string;
  variant: string | null;
  qty: number;
  unit_price: string;
  line_discount: string;
  line_total: string;
  supply_mode: SupplyMode;
  plant_code: string | null;
  atp_date: string | null;
  added_by: "customer" | "sales";
  requires_install: boolean;
};

export type StockShortage = { matnr: string; name: string; need: number; available: number; plant_code: string | null; stale: boolean; supply_mode: string };

export type Quotation = {
  id: string;
  quotation_no: string;
  preso_no: string | null;
  status: "issued" | "paid" | "converted" | "expired" | "cancelled";
  channel: "online" | "in_store_assisted";
  customer: { id?: string; name?: string; tier?: string | null; sap_customer_no?: string | null; phone?: string | null; email?: string | null };
  sales_name: string | null;
  sales_code: string | null;
  lines: QuotationLine[];
  discounts: { kind: string; code: string | null; title: string | null; amount: string }[];
  subtotal: string;
  discount_total: string;
  shipping_fee: string;
  install_fee: string;
  shipping_discount: string;
  vat: string;
  grand_total: string;
  deposit_amount: string;
  valid_until: string;
  pdf_url: string | null;
  ship_address: string | null;
  ship_postcode: string | null;
  ship_zone: string | null;
  slot_date: string | null;
  slot_period: "am" | "pm" | null;
  stock_warnings: StockShortage[] | null;
  sap_so_no: string | null;
  sap_sync_status: "pending" | "ok" | "failed";
  sap_sync_error: string | null;
  issued_at: string;
  paid_at: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  link_token: string | null;
};

// ---------- payment ----------
export type PaymentMethod = "qr_promptpay" | "card" | "installment" | "link";

export type Payment = {
  payment_no: string;
  quotation_no: string;
  method: PaymentMethod;
  kind: "full" | "deposit";
  amount: string;
  status: "pending" | "paid" | "failed" | "expired" | "cancelled";
  qr_payload: string | null;
  pay_url: string | null;
  expires_at: string;
  paid_at: string | null;
  sap_so_no: string | null;
  sap_sync_status: "pending" | "ok" | "failed";
  quotation_status: Quotation["status"];
};

export type SyncJob = {
  quotation_no: string;
  customer_name: string | null;
  grand_total: string;
  status: "pending" | "ok" | "failed";
  attempts: number;
  last_error: string | null;
  next_retry_at: string;
  sap_so_no: string | null;
  paid_at: string | null;
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

// ---------- ประวัติ + สินค้าขายดี (STEP 10) ----------
export type OrderLine = { matnr: string; name: string; qty: number; unit_price: string; line_total: string };
export type OrderHistory = {
  so_no: string;
  order_date: string;
  status: "confirmed" | "in_production" | "shipping" | "delivered" | "cancelled";
  channel: string;
  branch: string | null;
  grand_total: string;
  delivery_date: string | null;
  synced_at: string;
  lines: OrderLine[];
};
