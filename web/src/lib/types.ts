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

/** สีอื่นของรุ่นเดียวกัน — ต้นทางแยกทุกสีเป็นคนละ MATNR ปุ่มสีจึงเป็นลิงก์ไปอีกหน้าสินค้า */
export type ColorOption = {
  matnr: string;
  color: string | null;
  name_th: string;
  image_url: string | null;
  price: string;
};

export type MaterialDetail = MaterialCard & {
  barcode: string | null;
  description: string | null;
  color: string | null;
  style: string | null;
  volume_m3: string | null;
  weight_kg: string | null;
  sold_qty: number;
  colors: ColorOption[];
  /** หมวดของสินค้านี้ + หมวดพี่น้อง — ใช้เป็นชิปสลับใน "สินค้าที่เกี่ยวข้อง" */
  related_categories: { id: string; name_th: string }[];
  synced_at: string;
};

export type BrandFacet = { id: string; name: string; count: number };
export type Facets = { brands: BrandFacet[]; price_min: number | null; price_max: number | null };
export type SearchOut = { items: MaterialCard[]; total: number; q: string | null; category: string | null; facets?: Facets | null };

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

// ---------- เช็คของกับ SAP ----------
// ยิงทั้งตะกร้าครั้งเดียว (ยิงทีละชิ้นจะเห็นของซ้ำแล้วขายเกิน) · ไม่มีสาขา — SAP ตัวนี้ไม่บอก plant
export type AvailStatus = "full" | "split" | "short" | "none" | "unknown";

export type AvailabilityItem = {
  item_id: string | null;
  matnr: string;
  name: string;
  qty: number;
  status: AvailStatus;
  label: string;
  ready_qty: number;
  ready_date: string | null;
  later_qty: number;
  later_date: string | null;
  short_qty: number;
  sap_name: string | null;
  sap_unit_price: string | null;
  sap_amount: string | null;
  sap_discount_percent: number | null;
  our_amount: string | null;
  price_diff: string | null;
};

export type Availability = {
  cart_id: string;
  checked_at: string;
  req_date: string;
  customer_no: string;
  is_walkin: boolean;
  source: "sap" | "mock";
  all_ok: boolean;
  message: string;
  items: AvailabilityItem[];
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
  selected: boolean; // ติ๊กในหน้าตะกร้า = คิดเงินรอบนี้
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
  ship_area: string | null;
  ship_source: string;
  ship_weight_kg: string | null;
  ship_needs_review: boolean;
  ship_warnings: string[];
  ship_trace: { rule: string; name?: string; priority?: number; matched: boolean; reason: string; weight_kg?: string }[];
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
  count: number; // จำนวนชิ้นเฉพาะรายการที่ติ๊ก
  subtotal: string; // ยอดเฉพาะรายการที่ติ๊ก
  pending_count: number;
  all_count: number; // จำนวนชิ้นทั้งตะกร้า (ป้ายบนหัวเว็บ)
  item_count: number; // จำนวนรายการทั้งตะกร้า
  selected_count: number; // จำนวนรายการที่ติ๊กไว้
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
/** ภาพจริงจาก Magento CMS (ตาราง home_media) — ไม่มีเมื่อยังไม่ได้รัน sync_home_media */
export type MediaTile = { id: string; label: string | null; alt: string | null; image: string; image_mb: string | null; href: string };
export type HomeContent = {
  // hero_slides มาได้ 2 ทาง: ภาพจริงจาก CMS (มี image) หรือกล่อง placeholder จาก home.json
  hero_slides: ({ id: string; href: string } & Partial<MediaTile> & Partial<{ tag: string; title: string; note: string; cta: string; art: string }>)[];
  promo_cards: { tag: string; title: string; note: string; href: string }[];
  category_tiles: { label: string; category: string }[];
  top_categories?: MediaTile[];
  inspirations?: MediaTile[];
  inspire_tabs?: { key: string; label: string; items: MediaTile[] }[];
  brand_tiles?: MediaTile[];
  new_collections: NavLink[];
  room_rows: { label: string; room: string; href?: string; items: MaterialCard[] }[];
  rooms: { label: string; room: string }[];
  main_nav: { label: string; href?: string; items: NavLink[] }[];
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

// ---------- ที่อยู่ไทย (/geo) ----------
export type Province = {
  province_id: number;
  name_th: string;
  name_en: string | null;
  area_id: number | null;
  postcode: string; // รหัสตัวแทน ใช้ประเมินค่าส่งคร่าวๆ ก่อนรู้ที่อยู่เต็ม
  serviceable: boolean;
};
export type District = { district_id: number; name_th: string; name_en: string | null; province_id: number; serviceable: boolean };
export type Subdistrict = {
  subdistrict_id: number;
  name_th: string;
  name_en: string | null;
  district_id: number;
  zipcode: string;
  area_id: number | null;
  is_blocked: boolean;
};
export type PostcodeHit = {
  zipcode: string;
  subdistrict_id: number;
  subdistrict_th: string;
  district_id: number;
  district_th: string;
  province_id: number;
  province_th: string;
  area_id: number | null;
  is_blocked: boolean;
};
