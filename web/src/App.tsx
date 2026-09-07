import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/layout/Layout";
import { AuthProvider } from "./lib/auth";
import { CartProvider } from "./lib/cart";
import { ContentProvider } from "./lib/content";
import { SalesProvider } from "./lib/sales";
import AccountPage from "./pages/AccountPage";
import ApprovalsPage from "./pages/ApprovalsPage";
import CartPage from "./pages/CartPage";
import CheckoutPage from "./pages/CheckoutPage";
import HomePage from "./pages/HomePage";
import PresosPage from "./pages/PresosPage";
import PayPage from "./pages/PayPage";
import ProductPage from "./pages/ProductPage";
import QuotationPage from "./pages/QuotationPage";
import SalesPage from "./pages/SalesPage";
import SapSyncPage from "./pages/SapSyncPage";
import SearchPage from "./pages/SearchPage";
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

export default function App() {
  return (
    <AuthProvider>
      <ContentProvider>
        <CartProvider>
          <SalesProvider>
            <BrowserRouter>
              <Routes>
                <Route element={<Layout />}>
                  <Route path="/" element={<HomePage />} />
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
                  <Route path="*" element={<NotFound />} />
                </Route>
              </Routes>
            </BrowserRouter>
          </SalesProvider>
        </CartProvider>
      </ContentProvider>
    </AuthProvider>
  );
}
