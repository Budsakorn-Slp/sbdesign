import { Outlet } from "react-router-dom";
import { useCart } from "../../lib/cart";
import { useSales } from "../../lib/sales";
import LoginModal from "../LoginModal";
import Footer from "./Footer";
import Header from "./Header";

export default function Layout() {
  const { count } = useCart();
  const sales = useSales();
  const salesCount = sales.enabled ? sales.sessions.reduce((n, s) => n + s.count, 0) : 0;
  return (
    <div className="app">
      <Header cartCount={sales.enabled ? salesCount : count} cartHref={sales.enabled ? "/sales" : "/cart"} />
      <div className="app-body">
        <Outlet />
      </div>
      <Footer />
      <LoginModal />
    </div>
  );
}
