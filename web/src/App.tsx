import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import Icon from "./components/Icon";
import LoginModal from "./components/LoginModal";
import { AuthProvider, ROLE_PERMS, useAuth } from "./lib/auth";

function Placeholder() {
  const auth = useAuth();
  const perms = ROLE_PERMS[auth.role];
  return (
    <main className="container" style={{ padding: "48px 0" }}>
      <h1 style={{ fontSize: 28, margin: "0 0 4px" }}>SB Design Square</h1>
      <p className="muted" style={{ margin: "0 0 24px" }}>STEP 1 — Auth + Roles · หน้าแรกจริงจะมาใน STEP 2</p>
      <div className="card" style={{ maxWidth: 520 }}>
        <div className="row between">
          <div>
            <div className="muted small">บัญชีที่ใช้อยู่</div>
            <div style={{ fontWeight: 600 }}>
              {auth.user ? `${auth.user.name} · ${auth.user.role}${auth.user.staff_code ? " · " + auth.user.staff_code : ""}${auth.user.tier ? " · " + auth.user.tier : ""}` : "ผู้เยี่ยมชม (ไม่ล็อกอิน)"}
            </div>
          </div>
          {auth.user ? (
            <button className="btn" onClick={() => auth.logout()}>ออก</button>
          ) : (
            <button className="btn primary" onClick={auth.openLogin}>
              <Icon name="login" size={18} /> เข้าสู่ระบบ
            </button>
          )}
        </div>
        <ul className="perm-list">
          {perms.map((p) => (
            <li key={p.label} className={p.ok ? "ok" : "no"}>
              <Icon name={p.ok ? "check_circle" : "block"} size={18} />
              {p.label}
            </li>
          ))}
        </ul>
      </div>
      <p className="muted small" style={{ marginTop: 16 }}>
        <Link to="/">หน้าแรก</Link>
      </p>
    </main>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="*" element={<Placeholder />} />
        </Routes>
        <LoginModal />
      </BrowserRouter>
    </AuthProvider>
  );
}
