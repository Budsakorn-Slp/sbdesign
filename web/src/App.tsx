import InfoPage from "./pages/InfoPage";
import { lazy } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import BareLayout from "./components/layout/BareLayout";
import Layout from "./components/layout/Layout";
import { AuthProvider } from "./lib/auth";
import { CartProvider } from "./lib/cart";
import { ContentProvider } from "./lib/content";
import { LangProvider } from "./lib/i18n";
import { SalesProvider } from "./lib/sales";
import HomePage from "./pages/HomePage";

/* หน้าที่เหลือแยกเป็นไฟล์ของตัวเอง โหลดตอนกดเข้าไปจริงเท่านั้น (code splitting)
   เดิมรวมทุกหน้าไว้ก้อนเดียว ลูกค้าที่แค่เปิดมาดูสินค้าต้องโหลดหน้าเซลล์ · ใบเสนอราคา ·
   จ่ายเงิน · อนุมัติส่วนลด · คิว SAP ไปด้วยทั้งที่ไม่มีวันได้ใช้
   หน้าแรกไม่แยก เพราะเป็นหน้าที่คนเข้ามากที่สุด แยกแล้วจะเห็นโครงเปล่าแวบหนึ่งก่อนเสมอ */
const LoginPage = lazy(() => import("./pages/LoginPage"));
const StaffLoginPage = lazy(() => import("./pages/StaffLoginPage"));
const SearchPage = lazy(() => import("./pages/SearchPage"));
const ProductPage = lazy(() => import("./pages/ProductPage"));
const AccountPage = lazy(() => import("./pages/AccountPage"));
const CartPage = lazy(() => import("./pages/CartPage"));
const CheckoutPage = lazy(() => import("./pages/CheckoutPage"));
const PayPage = lazy(() => import("./pages/PayPage"));
const QuotationPage = lazy(() => import("./pages/QuotationPage"));
const SalesPage = lazy(() => import("./pages/SalesPage"));
const PresosPage = lazy(() => import("./pages/PresosPage"));
const ApprovalsPage = lazy(() => import("./pages/ApprovalsPage"));
const SapSyncPage = lazy(() => import("./pages/SapSyncPage"));
import "./styles/layout.css";
import "./styles/pages.css";
import "./styles/cart.css";
import "./styles/sales.css";

function NotFound() {
  return (
    <main className="container sec">
      <h1>ไม่พบหน้านี้</h1>
    </main>
  );
}

// Router อยู่นอกสุด (นอก provider ทั้งหมด) เพื่อให้ provider ข้างในเรียก navigate ได้ —
// auth.openLogin พาไปหน้า /login แทนการเปิดกล่องทับหน้าเดิม
export default function App() {
  return (
    <BrowserRouter>
      <LangProvider>
      <AuthProvider>
        <ContentProvider>
          <CartProvider>
            <SalesProvider>
              <Routes>
                {/* ทางเข้าของพนักงาน — อยู่นอก Layout ลูกค้าโดยตั้งใจ ไม่มีช่องค้นหาสินค้า
                    เมนูหมวด ตะกร้า หรือกล่องชวนสมัครสมาชิกมาอยู่รอบๆ ฟอร์มรหัสพนักงาน */}
                <Route element={<BareLayout />}>
                  <Route path="/staff" element={<StaffLoginPage />} />
                </Route>
                <Route element={<Layout />}>
                  <Route path="/" element={<HomePage />} />
                  <Route path="/login" element={<LoginPage />} />
                  <Route path="/search" element={<SearchPage />} />
                  <Route path="/p/:matnr" element={<ProductPage />} />
                  <Route path="/account" element={<AccountPage />} />
                  <Route path="/account/:tab" element={<AccountPage />} />
                  <Route path="/cart" element={<CartPage />} />
                  <Route path="/checkout" element={<CheckoutPage />} />
                  <Route path="/sales" element={<SalesPage />} />
                  <Route path="/sales/presos" element={<PresosPage />} />
                  <Route path="/sales/quotations/:no" element={<QuotationPage mode="sales" />} />
                  <Route path="/q/:no" element={<QuotationPage mode="customer" />} />
                  <Route path="/quotations/:no" element={<QuotationPage mode="customer" />} />
                  <Route path="/pay/:no" element={<PayPage />} />
                  <Route path="/manager/approvals" element={<ApprovalsPage />} />
                  <Route path="/manager/sap-sync" element={<SapSyncPage />} />
                  {/* หน้าเนื้อหาคงที่จาก CMS (/warranty, /career, ...) — ต้องอยู่ก่อน * เท่านั้น
                      และอยู่ท้ายสุดของเส้นทางที่เจาะจง ไม่งั้นมันจะกลืนเส้นทางอื่นที่มีชั้นเดียว */}
                  <Route path="/:slug" element={<InfoPage />} />
                  <Route path="*" element={<NotFound />} />
                </Route>
              </Routes>
            </SalesProvider>
          </CartProvider>
        </ContentProvider>
      </AuthProvider>
      </LangProvider>
    </BrowserRouter>
  );
}
