import { Outlet } from "react-router-dom";
import LoginModal from "../LoginModal";
import Footer from "./Footer";
import Header from "./Header";

export default function Layout({ cartCount = 0 }: { cartCount?: number }) {
  return (
    <div className="app">
      <Header cartCount={cartCount} />
      <div className="app-body">
        <Outlet />
      </div>
      <Footer />
      <LoginModal />
    </div>
  );
}
