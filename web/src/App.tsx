import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/layout/Layout";
import { AuthProvider } from "./lib/auth";
import { ContentProvider } from "./lib/content";
import HomePage from "./pages/HomePage";
import ProductPage from "./pages/ProductPage";
import SearchPage from "./pages/SearchPage";
import "./styles/layout.css";
import "./styles/pages.css";

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
        <BrowserRouter>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<HomePage />} />
              <Route path="/search" element={<SearchPage />} />
              <Route path="/p/:matnr" element={<ProductPage />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ContentProvider>
    </AuthProvider>
  );
}
