import { Outlet } from "react-router-dom";
import { useCart } from "../../lib/cart";
import LoginModal from "../LoginModal";
import Footer from "./Footer";
import Header from "./Header";

export default function Layout() {
  const { count } = useCart();
  return (
    <div className="app">
      <Header cartCount={count} />
      <div className="app-body">
        <Outlet />
      </div>
      <Footer />
      <LoginModal />
    </div>
  );
}
