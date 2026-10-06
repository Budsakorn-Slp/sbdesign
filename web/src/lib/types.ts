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
  points: number;
  is_guest: boolean;
  default_address: string | null;
  default_postcode: string | null;
  /** ที่อยู่ในทะเบียนสมาชิกฝั่ง SAP — อ่านอย่างเดียว คนละอันกับสมุดที่อยู่จัดส่ง */
  sap_address: string | null;
  sap_postcode: string | null;
  /** ตั้งรหัสผ่านไว้แล้ว — ใช้ซ่อนช่อง "ตั้งรหัสผ่าน" ที่ถ้ากดจะได้ 409 */
  has_password: boolean;
  /** ยังไม่เคยผ่านขั้น "ตั้งค่าบัญชี" หลังล็อกอินครั้งแรก — ผูกเลขสมาชิกแล้วจะเป็น false เสมอ */
  needs_profile: boolean;
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

/** ยอดของรวมทุกสาขาจาก SAP ที่ cache ไว้โชว์บนการ์ด — ไม่ใช่ยอดสด ยืนยันจริงตอนสั่งซื้อ */
export type ProductStock = {
  ready_qty: number;
  later_qty: number;
  later_date: string | null;
  /** สั่งทำ — สั่งได้เสมอ ไม่ต้องรอสต็อก (SAP ไม่คุมสต็อกสินค้ากลุ่มนี้) */
  made_to_order: boolean;
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
  compare_at_price: string | null;
  discount_percent: number | null;
  requires_install: boolean;
  is_takeaway_ok: boolean;
  is_new: boolean;
  /** ของที่ตั้งโชว์หน้าร้าน — backend ตัดสินจากกลุ่ม MATNR ให้แล้ว */
  is_display?: boolean;
  /** ของตัวโชว์/ฝากขาย — ซื้อได้ที่สาขาเท่านั้น และซื้อแล้วไม่รับเปลี่ยนคืน */
  pickup_only?: boolean;
  tags: string[];
  stock: ProductStock | null;
};

/** สีอื่นของรุ่นเดียวกัน — ต้นทางแยกทุกสีเป็นคนละ MATNR ปุ่มสีจึงเป็นลิงก์ไปอีกหน้าสินค้า */
/** ตัวเลือกหนึ่งปุ่มบนหน้าสินค้า — ขนาด หรือ สี · กดแล้วไป MATNR ตัวนั้น */
export type VariantOption = {
  label: string;
  matnr: string;
  image_url: string | null;
  price: string | null;
};

/** สาขาที่มีของตัวนี้ — ชื่อมาจาก SAP ตรงๆ ไม่รวมคลัง/ระดับบริษัท */
export type StockSite = { plant_code: string; name: string; qty: number };

export type MaterialDetail = MaterialCard & {
  barcode: string | null;
  description: string | null;
  /** LONG_DESC — คำบรรยายเต็ม (HTML ที่ล้างมาจากฝั่ง ETL แล้ว) */
  description_long?: string | null;
  color: string | null;
  style: string | null;
  volume_m3: string | null;
  weight_kg: string | null;
  sold_qty: number;
  /** รูปทั้งหมดของสินค้าตัวนี้ เรียงตามลำดับของต้นทาง (ใบหลักมาก่อน) */
  images: string[];
  /** แกนขนาด (จาก MVGR5T) · ว่างถ้ารุ่นนี้มีขนาดเดียว */
  sizes: VariantOption[];
  /** แกนสี (จาก MVGR6T) · ว่างถ้ารุ่นนี้มีสีเดียว */
  colors: VariantOption[];
  /** หมวดของสินค้านี้ + หมวดพี่น้อง — ใช้เป็นชิปสลับใน "สินค้าที่เกี่ยวข้อง" */
  related_categories: { id: string; name_th: string }[];
  stock_sites: StockSite[];
  synced_at: string;
};

export type BrandFacet = { id: string; name: string; count: number };
export type Facets = { brands: BrandFacet[]; price_min: number | null; price_max: number | null };
/** แบรนด์บนหน้าแรก — รูปคือสินค้าขายดีสุดของแบรนด์นั้น (ไม่มีไฟล์โลโก้ผูกกับรหัสแบรนด์) */
export type HomeBrand = BrandFacet & { matnr: string | null; image_url: string | null };
/** สิ่งที่ระบบตีความจากประโยคค้นหา — "ตู้เสื้อผ้าสีแดง สูง 180" → หมวด/สี/ขนาด */
export type Understood = {
  labels: string[];
  /** เงื่อนไขที่ต้องยอมตัดทิ้งถึงจะเจอของ (specs | color) */
  dropped: string[];
  category_id: string | null;
  color: string | null;
  min_price: number | null;
  max_price: number | null;
};

export type SearchOut = {
  items: MaterialCard[];
  total: number;
  q: string | null;
  category: string | null;
  facets?: Facets | null;
  /** ระบบแก้ตัวสะกดให้ถึงจะเจอของ */
  corrected?: string | null;
  understood?: Understood | null;
  /** ต้องผ่อนเป็น "เข้าคำใดคำหนึ่ง" ผลจึงไม่ตรงครบทุกคำ */
  relaxed?: boolean;
};

/** ข้อมูลสมาชิกเท่าที่เห็นได้ก่อนพิสูจน์ตัวตน — เบอร์/อีเมลปิดบังมาจาก backend แล้ว */
export type MemberCard = {
  sap_customer_no: string;
  name: string;
  points: number;
  phone_masked: string;
  email_masked: string | null;
  /** true = เบอร์ตรงกับที่ยืนยันไว้ กดผูกได้เลย · false = ต้องยืนยัน OTP ที่เบอร์ในทะเบียนก่อน */
  can_link_now: boolean;
};

export type MemberLinkStart = { sap_customer_no: string; requires_otp: boolean; member: MemberCard };

export type SuggestItem = { kind: "term" | "category" | "brand"; label: string; href: string };
export type SuggestOut = { q: string; suggestions: SuggestItem[]; items: MaterialCard[] };

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

// ---------- เช็คสต็อก (SAP) ----------
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
  /** ยอดของจาก cache ไว้โชว์ป้ายสต็อกในตะกร้า (ไม่ใช่ยอดสด) */
  stock: ProductStock | null;
  /** กลุ่มสินค้าจากตัวขึ้นต้น MATNR — regular (19) · display (20) · consign (25) */
  group: string | null;
  /** ใส่ตะกร้าได้ แต่ยังชำระเงินออนไลน์ไม่ได้ ต้องไปรับที่สาขา */
  pickup_only: boolean;
  /** บรรทัดค่าบริการขนส่งที่พนักงานเปิด Mat ไว้ ไม่ใช่สินค้าที่ลูกค้าหยิบ
   *  หลังบ้านเป็นคนบอก (อ่านจากไฟล์กฎ) หน้าเว็บจึงไม่ต้องถือลิสต์รหัสเอง */
  is_charge?: boolean;
  /** tier = ตามยอดบิล · extra = ค่าส่งเพิ่มจากปลายทาง */
  charge_role?: "tier" | "extra" | null;
  selected: boolean; // ติ๊กในหน้าตะกร้า = คิดเงินรอบนี้
  supply_mode: SupplyMode;
  plant_code: string | null;
  atp_date: string | null;
  requires_install: boolean;
  note: string | null;
  /** สาขาที่มีของตัวจริงให้ไปดู — มีเฉพาะสินค้าตัวโชว์ที่ต้องรับที่สาขา */
  show_at_sites: StockSite[];
};

export type CartPerson = {
  id: string;
  name: string;
  points: number;
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
  /** true = คูปองที่ต้องเลือก/กรอกโค้ด · false = โปรฯ ที่ระบบเช็คจากของในตะกร้าให้เอง */
  requires_code: boolean;
};

export type EvaluateOut = {
  cart_id: string;
  customer_name: string | null;
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
  /** ด่านก่อนบันทึกใบ PRE — มาเฉพาะตะกร้าที่พนักงานถือ */
  preso: PresoReady | null;
  /** หมายเหตุหลักทั้งตะกร้า — คนละช่องกับ note ของแต่ละรายการ */
  overall_remark?: string | null;
  /** พนักงานร่วมบิล Z1-ZK */
  staff?: CartStaff[];
};

export type CartStaff = { role_code: string; role_name: string; user_id: string | null; employee_code: string; employee_name: string };
export type StaffRole = { code: string; name: string };
export type EmployeeRef = { user_id: string; employee_code: string; employee_name: string; branch_code: string | null; label: string };
export type StaffMe = { employee_code: string; employee_name: string; branch_code: string | null; branch_name: string | null; role: string; permissions: string[] };
export type StaffPhoto = {
  id: string; matnr: string; branch_code: string; url: string; width: number; height: number;
  owner_employee_code: string; owner_employee_name: string; created_at: string; updated_at: string | null;
  can_edit: boolean; can_delete: boolean; mine: boolean;
  /** แชร์ให้ลูกค้าเห็นแล้ว — อัปโหลดใหม่ยังเป็น false (เห็นเฉพาะพนักงาน) */
  is_public: boolean; shared_at: string | null;
};
export type BranchPhotos = { branch_code: string; branch_name: string; photos: { id: string; url: string; width: number; height: number }[] };
export type StaffPhotoAudit = {
  image_id: string; matnr: string; branch_code: string; image_owner_employee: string; action: "CREATE" | "UPDATE" | "DELETE" | "SHARE" | "UNSHARE";
  action_by_employee: string; action_by_role: string; action_at: string; old_image_url: string | null; new_image_url: string | null;
};
export type QuotationTemplate = {
  employee_code: string; employee_name: string; branch_code: string | null; branch_name: string | null;
  display_name: string | null; phone: string | null; logo_url: string | null; bank_accounts: string | null;
  footer_terms: string | null; standard_remark: string | null; updated_at: string | null; month_end_preview: string;
};

/** หนึ่งด่านในผังงานหน้าร้าน (ลูกค้า → ข้อมูล → สต็อก → โปรฯ → คิวส่ง) */
export type PresoStepKey = "customer" | "stock" | "promo" | "delivery";
export type PresoStep = {
  key: PresoStepKey;
  title: string;
  ok: boolean;
  note: string;
  /** ยังไม่ถึงคิว เพราะด่านก่อนหน้ายังไม่ผ่าน */
  blocked: boolean;
};
export type PresoReady = {
  ready: boolean;
  next: PresoStepKey | null;
  message: string;
  steps: PresoStep[];
};

/** ที่อยู่จัดส่งหนึ่งใบในสมุดที่อยู่ของลูกค้า */
export type SavedAddress = {
  id: string;
  label: string | null;
  receiver: string;
  phone: string;
  address: string;
  sub: string | null;
  district: string | null;
  province: string | null;
  postcode: string;
  note: string | null;
  is_default: boolean;
  /** ที่อยู่รวมบรรทัดเดียว — ใช้โชว์และส่งให้ระบบคิดค่าส่ง */
  one_line: string;
};

// ---------- preso / quotation ----------
export type PresoSummary = {
  id: string;
  preso_no: string;
  status: "draft" | "quoted" | "expired" | "cancelled";
  cart_id: string;
  customer_name: string | null;
  sales_name: string | null;
  item_count: number;
  grand_total: string;
  note: string | null;
  quotation_no: string | null;
  quotation_status: string | null;
  /** token เปิดเอกสารในแท็บใหม่ (แท็บใหม่ไม่มี header ของหน้าเว็บติดไปด้วย) · พนักงานเท่านั้น */
  quotation_token: string | null;
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

// matnr/supply_mode เป็น null ได้ตอน SAP ล่ม — ตอนนั้นไม่ได้ขาดสินค้าตัวไหนเป็นตัวๆ
// แต่เป็น "เช็คไม่ได้ทั้งใบ" ซึ่งก็ต้องไม่นับว่าของพอ (ดู live_stock_check ฝั่ง backend)
export type StockShortage = {
  matnr: string | null; name: string; need: number; available: number;
  plant_code: string | null; stale: boolean; supply_mode: string | null;
  status?: "short" | "none" | "unknown"; label?: string; sap_error?: string;
  ready_qty?: number; ready_date?: string | null; later_qty?: number; later_date?: string | null;
};

export type Quotation = {
  id: string;
  quotation_no: string;
  preso_no: string | null;
  status: "issued" | "paid" | "converted" | "expired" | "cancelled";
  channel: "online" | "in_store_assisted";
  customer: { id?: string; name?: string; points?: number; sap_customer_no?: string | null; phone?: string | null; email?: string | null };
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
  /** เหตุผลที่ธนาคารปฏิเสธ — หน้าผลการชำระเงินต้องบอกให้ตรง ไม่ใช่ "ไม่สำเร็จ" ลอยๆ */
  failed_reason: string | null;
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
export type NavLink = { label: string; label_en?: string | null; href: string };
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
  /** groups = เมนู 3 ชั้น (ห้องที่ยกหมวดมาจากเว็บจริงแล้ว) · items = เมนู 2 ชั้นแบบเดิม */
  main_nav: { label: string; label_en?: string | null; href?: string; items: NavLink[]; groups?: { label: string; label_en?: string | null; href: string; items: NavLink[] }[] }[];
  footer_promos: { head: string; body: string; cta: string; href: string }[];
  footer_cols: { head: string; items: NavLink[] }[];
  payments: string[];
  legal_links: NavLink[];
  support_line: string;
  free_shipping_note: string;
  categories: Category[];
  new_products: MaterialCard[];
  deals: MaterialCard[];
  bestsellers: MaterialCard[];
  /** แบรนด์ที่มีสินค้าขายอยู่จริง (พร้อมจำนวน + รูปสินค้าขายดีของแบรนด์) — backend กรองมาให้แล้ว */
  brands: HomeBrand[];
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

/** คำสั่งซื้อที่รอชำระเงิน — แท็บ "รอชำระเงิน" กับตัวเลขบนกระดิ่งอ่านจากตัวนี้ */
export type PendingPayment = {
  quotation_no: string;
  payment_no: string | null;
  amount: string;
  method: string | null;
  issued_at: string;
  expires_at: string | null;
  /** ติดลบได้ถ้าเพิ่งหมดพอดี — หน้าเว็บปัดเป็น 0 เอง */
  seconds_left: number | null;
  item_count: number;
  first_item: string | null;
};
