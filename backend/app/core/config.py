from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """ค่า config ทั้งหมดอ่านจาก env (ดู .env.example ที่ root)"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SB Sales App API"
    # ระดับ log ของโค้ดเรา — INFO จะเห็นบรรทัดสำคัญอย่าง [MOCK SMS] ที่พิมพ์รหัส OTP ออกมา
    log_level: str = "INFO"
    database_url: str = "sqlite:///./sbdesign.db"
    # แหล่งข้อมูลสินค้า (ฐานเว็บ sbdesignsquare) — อ่านอย่างเดียว ไม่ใช่ฐานของแอป
    sbweb_database_url: str = ""
    # ฐาน Magento (10.9.12.67) — ต้นทางรูปสินค้า อ่านอย่างเดียว
    # ใส่แยกเป็นตัวๆ ดีกว่าเขียนเป็น URL เพราะรหัสผ่านมี @ อยู่ข้างใน
    # ถ้ายัดลง URL ต้อง %40 ให้ครบทุกตัว พลาดตัวเดียวมันจะตัด host ผิด
    magento_host: str = ""
    magento_port: int = 3306
    magento_user: str = ""
    magento_password: str = ""
    magento_db: str = "magento3"
    magento_database_url: str = ""  # ใส่ตรงนี้แทนก็ได้ ถ้า encode เองแล้ว

    @property
    def magento_url(self) -> str:
        # ตัวแปรแยกมาก่อนเสมอ — MAGENTO_DATABASE_URL เป็นทางเลือกสำรอง
        # ถ้าให้ URL ชนะ บรรทัดเก่าที่ลืมลบจะแอบถูกใช้แทนโดยไม่มีอะไรเตือน
        if not self.magento_host:
            return self.magento_database_url
        url = URL.create(
            "mysql+pymysql",
            username=self.magento_user,
            password=self.magento_password,
            host=self.magento_host,
            port=self.magento_port,
            database=self.magento_db,
            query={"charset": "utf8mb4"},
        )
        # str(URL) ปิดรหัสผ่านเป็น *** — ถ้าใช้ตรงๆ จะกลายเป็นส่ง "***" ไปเป็นรหัสจริง
        return url.render_as_string(hide_password=False)
    jwt_secret: str = "dev-only-secret-change-me-in-production-please"
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    sap_mode: str = "mock"  # mock | http
    sap_base_url: str = "http://localhost:9000"
    sap_timeout_seconds: float = 3.0
    # เช็คสต็อก (ZAIBAPI_MATERIAL_AVAILABILITY ผ่าน RFC gateway)
    # ว่าง = ใช้ mock — dev/test รันได้โดยไม่ต้องต่อ SAP จริง
    sap_avail_url: str = ""
    sap_api_key: str = ""
    sap_avail_timeout_seconds: float = 20.0  # ของจริงตอบ ~0.3 วิ แต่ตะกร้าใหญ่ SAP คิดนานกว่านั้นมาก
    # เช็คสต็อกรวมทุกสาขา (ZAIBAPI_MATERIAL_STOCK) — ใช้เติมจำนวนของให้หน้ารายการสินค้า
    # คนละตัวกับ sap_avail_url: อันนั้นถาม "ลูกค้ารายนี้รับของวันนั้นได้กี่ชิ้น" ต้องระบุลูกค้า/สาขา
    # อันนี้ถาม "ของทั้งบริษัทมีเท่าไหร่" ใส่แค่รหัสสินค้า · ว่าง = ใช้ mock
    sap_stock_url: str = ""
    sap_stock_timeout_seconds: float = 120.0  # วัดจริง 20 รหัส ~7 วิ · 40 รหัส ~10 วิ
    sap_walkin_customer: str = "1100467950"  # ตะกร้าที่ยังไม่ผูกลูกค้า — SAP บังคับต้องมี CUSTOMER เสมอ
    sap_order_type: str = "9202"
    sap_sales_org: str = "9000"
    sap_distr_chan: str = "18"
    sap_division: str = "20"
    sap_avail_lead_days: int = 7  # REQ_DATE = วันนี้ + 7
    # ตอนนี้เช็คสต็อกส่งไปแต่รหัสสินค้า ยังไม่ส่งเลขลูกค้าจริง — ใช้ลูกค้าทั่วไปทุกใบ
    # เพราะ API ฝั่ง SAP ที่รับข้อมูลลูกค้าทั้งชุด (สมัคร/ผูกเลขลูกค้า) ยังไม่พร้อม
    # เลขลูกค้าของเราจึงยังไม่มีอยู่ใน SAP ส่งไปก็โดนทิ้งทั้งใบ (ตอบกลับเปล่า)
    # พอ API พร้อมแล้วเปิดเป็น true ระบบจะส่งเลขลูกค้าจริงไปด้วยทันที
    sap_avail_send_customer_no: bool = False
    # จำนวนของที่โชว์ในหน้ารายการสินค้า — อ่านจาก availability_cache ไม่ได้ยิง SAP สดตอนเปิดหน้า
    stock_cache_ttl_minutes: int = 60
    stock_batch_size: int = 20  # กี่รหัสต่อการยิง SAP หนึ่งครั้ง
    # สร้าง Sales Order (ดู app/integrations/sap/http.py + docs/sap-sales-order.md)
    # ว่าง = ยังใช้ mock · ฝั่งหลังบ้านเปิด endpoint เมื่อไหร่ใส่ URL แล้วตั้ง SAP_MODE=http
    # ---------- ราคาสินค้าจาก SAP (ZAIBAPI_MATERIAL_GET_ALL) ----------
    # งานรายวันแบบยกชุด คนละเรื่องกับ sap_avail_url/sap_stock_url ซึ่งถามสดตอนลูกค้ากดปุ่ม
    sap_catalog_url: str = ""
    # ช่วงกว้างใช้เวลาเป็นนาที (ช่วง 19xxxxxxx ทั้งก้อน ~200 วิ) ตั้งเผื่อไว้มาก
    sap_catalog_timeout_seconds: float = 600.0

    sap_so_url: str = ""
    sap_so_timeout_seconds: float = 30.0  # สร้างเอกสารช้ากว่าการอ่าน เผื่อเวลาไว้มากกว่า avail
    # กลุ่มสินค้าที่ให้โชว์บนเว็บ ตัดสินจากตัวขึ้นต้นของ MATNR
    # 19 ขายปกติ · 20 ตัวโชว์ · 25 ฝากวางขาย · 27 รวมห้อง — เอา 19/20/25 อนาคตเติมคั่นด้วย ,
    # ตัวที่ไม่เข้ากลุ่มจะ is_public = false: ลูกค้าไม่เห็น แต่เซลล์ยังค้นเจอไว้เช็คสต็อกหน้าร้าน
    catalog_matnr_prefixes: str = "19,20,25"
    # ชื่อกลุ่มที่หน้าเว็บเรียกใช้ได้ (?group=display) → ตัวขึ้นต้น MATNR ของกลุ่มนั้น
    # แยกไว้เพื่อไม่ให้หน้าเว็บต้องรู้เลขนำหน้า วันหลังเปลี่ยนเลขก็แก้ที่นี่ที่เดียว
    catalog_matnr_groups: str = "regular:19,display:20,consign:25"
    # กลุ่มที่ "ใส่ตะกร้าได้ แต่ยังชำระเงินออนไลน์ไม่ได้" — ของตัวโชว์ (20) กับของฝากขาย (25)
    # เป็นของชิ้นเดียวอยู่หน้าร้าน ต้องไปดู/รับที่สาขา ระบบจึงบอกสาขาที่มีของแทนการให้จ่ายเงิน
    # อนาคตเปิดขายออนไลน์ได้เมื่อไร แก้ค่านี้อย่างเดียว (เอาชื่อกลุ่มออก หรือใส่ "" = เปิดหมด)
    # ไม่ต้องแก้โค้ดที่ไหนอีก — ทุกด่านอ่านจากค่านี้ที่เดียว
    online_checkout_blocked_groups: str = "display,consign"
    sales_cart_ttl_hours: int = 4
    staff_discount_quota_percent: float = 3.0
    quotation_valid_days: int = 7
    # OTP_DEBUG=true จะส่งรหัสกลับมาใน response ให้เห็นบนหน้าจอ (สำหรับ dev/เทสเท่านั้น)
    # ห้ามเปิดบนโปรดักชันเด็ดขาด — ใครก็ขอ OTP ของเบอร์คนอื่นแล้วอ่านรหัสจาก response ได้
    otp_debug: bool = True
    # จำกัดว่า "โชว์รหัส OTP บนจอ" ใช้ได้กับเบอร์ไหนบ้าง — คั่นด้วยจุลภาค ว่าง = ทุกเบอร์
    #
    # ทำไมต้องมี: OTP_DEBUG เปล่าๆ คืนรหัสให้ "ทุกเบอร์ที่ขอ" ซึ่งแปลว่าใครก็ขอ OTP
    # ของเบอร์คนอื่นแล้วอ่านรหัสจาก response เพื่อยึดบัญชีได้ทันที
    # ใส่รายชื่อเบอร์ทดสอบไว้ จะเหลือความเสี่ยงเฉพาะบัญชีทดสอบที่เราคุมเอง
    # บัญชีลูกค้าจริงจะไม่มีทางได้รหัสทางนี้ ต้องรอ SMS จริงเท่านั้น
    otp_debug_phones: str = ""

    # ---------- ช่วงเปิดให้ทดสอบก่อนเปิดจริง (soft launch) ----------
    # true = หน้าเข้าสู่ระบบขึ้น "เร็ว ๆ นี้" และ "สมัครสมาชิก" ปิด
    #        เข้าได้เฉพาะบัญชีที่มีอยู่แล้ว (คนที่เราแจกรหัสให้)
    #
    # ต้องกันที่ฝั่งนี้ด้วย ไม่ใช่แค่ซ่อนปุ่มบนหน้าเว็บ — ระบบนี้ "สมัคร" กับ "เข้าสู่ระบบ"
    # เป็นทางเดียวกัน (ยืนยัน OTP ของเบอร์ที่ยังไม่มีบัญชี = ได้บัญชีใหม่ทันที)
    # ซ่อนแค่ปุ่มจึงไม่ได้กันอะไรเลย ใครยิง API เองก็สมัครได้อยู่ดี
    # รับมัดจำไหม — ปิดไว้ ตอนนี้ธุรกิจรับชำระเต็มจำนวนอย่างเดียว
    # ไม่ได้ลบทิ้งเพราะยอดมัดจำยังคิดและเก็บไว้ในใบเสนอราคาอยู่ (deposit_amount) พร้อมเปิดใช้
    # วันที่ตกลงเงื่อนไขกันได้ · เปิดแล้วทั้งปุ่มหน้าเว็บและ API จะกลับมาพร้อมกัน ไม่ต้องแก้โค้ด
    deposit_enabled: bool = False
    # ให้เซลล์กดลดราคาเองได้ไหม — ปิดไว้ ธุรกิจไม่ให้ส่วนลดพนักงานแล้ว
    # ส่วนลดทั้งหมดต้องมาจากโปรโมชั่นที่ตั้งไว้ ไม่ใช่ดุลพินิจหน้าร้าน
    # โค้ดกับด่านอนุมัติของผู้จัดการยังอยู่ครบ เปิดคืนได้วันที่นโยบายเปลี่ยน
    staff_discount_enabled: bool = False

    # ---------- ช่องทางรับชำระเงิน ----------
    # mock  = หน้าธนาคารจำลองของเราเอง (/pay/{no}/bank) ไม่มีเงินเคลื่อนไหวจริง
    # kbank = K-Payment Gateway ของกสิกร — ยังต่อไม่ได้ รอคีย์กับเอกสาร API
    #         ตั้งเป็น kbank โดยไม่ใส่คีย์ ระบบจะตีกลับพร้อมบอกว่าขาดอะไร ไม่ปล่อยเงียบ
    payment_provider: str = "mock"
    kbank_base_url: str = ""       # sandbox: https://dev-kpaymentgateway.kasikornbank.com
    kbank_merchant_id: str = ""
    kbank_public_key: str = ""     # ใช้กับ kpayment.js บนหน้าเว็บ (ไม่ลับ)
    kbank_secret_key: str = ""     # ฝั่งเซิร์ฟเวอร์เท่านั้น ห้ามส่งไปหน้าเว็บ
    kbank_timeout_seconds: float = 20.0

    # ---------- ท้ายใบเสนอราคา ----------
    # เงื่อนไขการชำระเงิน + บัญชีบริษัท · เป็นข้อความที่ลูกค้าใช้โอนเงินจริง จึงไม่ฝังในโค้ด
    # ใส่ใน .env แล้วแก้ได้โดยไม่ต้อง deploy · เว้นว่าง = ไม่พิมพ์ส่วนนั้นในเอกสาร
    # (ดีกว่าพิมพ์เลขบัญชีตัวอย่างค้างไว้แล้วมีคนโอนเงินไปผิดที่)
    # หัวเอกสาร — ชื่อ/ที่อยู่/เลขผู้เสียภาษีของบริษัท ตามที่ขึ้นบนใบรับคำสั่งซื้อของระบบเดิม
    # ค่าตั้งต้นถอดมาจากเอกสารจริง · ตรวจตัวเลขอีกรอบก่อนใช้ออกเอกสารให้ลูกค้าจริง
    company_name_th: str = "บริษัท เอสบี ดีไซน์สแควร์ จำกัด"
    company_name_en: str = "SB DESIGNSQUARE CO., LTD."
    company_address_th: str = "126/150 หมู่ที่ 1 ต.ปากเกร็ด อ.ปากเกร็ด จ.นนทบุรี 11120"
    company_address_en: str = "126/150 MOO 1, PAKKRET, NONTHABURI 11120"
    company_tax_id: str = "0125555022441"

    # เงื่อนไขท้ายใบ — ปล่อยว่างไว้จะใช้ข้อความมาตรฐานใน api/quotation_doc.py
    # ตั้งค่านี้เมื่อต้องการเขียนทับทั้งก้อน (คั่นแต่ละข้อด้วย | และขึ้นบรรทัดใหม่ด้วย ;)
    quotation_terms: str = ""
    invite_only: bool = False
    # dev | prod — prod จะปิดหน้าเอกสาร API, บังคับ cookie secure และใส่ security header
    # แยกจาก invite_only เพราะคนละเรื่อง: อันนั้นคือ "ใครสมัครได้" อันนี้คือ "เปิดสู่เน็ตจริงหรือยัง"
    app_env: str = "dev"
    # ข้อความบนหน้า "เร็ว ๆ นี้" — แก้ได้จาก env ไม่ต้อง build หน้าเว็บใหม่
    coming_soon_title: str = "เร็ว ๆ นี้"
    coming_soon_text: str = "เรากำลังเตรียมร้านค้าออนไลน์ให้พร้อมที่สุด อีกไม่นานเจอกันแน่นอน"

    # ---------- SMS gateway (ดู app/integrations/sms/) ----------
    sms_mode: str = "mock"  # mock = พิมพ์ออก console · http = ยิง REST API ของผู้ให้บริการ
    sms_url: str = ""
    sms_auth_header: str = "Authorization"
    sms_api_key: str = ""
    sms_field_to: str = "to"
    sms_field_text: str = "message"
    sms_field_sender: str = "sender"
    sms_sender: str = ""
    sms_phone_format: str = "local"  # local | intl | e164
    sms_timeout_seconds: float = 8.0
    sms_otp_template: str = "รหัสยืนยัน SB Design Square ของคุณคือ {code} (ใช้ได้ 5 นาที)"
    payment_webhook_secret: str = "payment-webhook-secret"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def otp_debug_for(self, digits: str) -> bool:
        """เบอร์นี้ขอดูรหัส OTP บนจอได้ไหม"""
        if not self.otp_debug:
            return False
        allow = [p.strip() for p in self.otp_debug_phones.split(",") if p.strip()]
        return not allow or digits in allow

    @property
    def is_prod(self) -> bool:
        return self.app_env.lower() in ("prod", "production")

    @property
    def otp_enabled(self) -> bool:
        """OTP ใช้ได้จริงไหม — ต้องส่ง SMS ได้ หรืออยู่โหมด debug ที่คืนรหัสมาบนจอ

        ถ้าทั้งสองอย่างไม่มี การกดปุ่ม OTP จะค้างอยู่ตรงหน้ากรอกรหัสที่ไม่มีวันมาถึง
        หน้าเว็บจึงต้องซ่อนปุ่มนั้นไปเลย ไม่ใช่ปล่อยให้กดแล้วตัน
        """
        return self.sms_mode.lower() != "mock" or self.otp_debug

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
