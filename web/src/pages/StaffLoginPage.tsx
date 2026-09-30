import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import AuthShell from "../components/AuthShell";
import Icon from "../components/Icon";
import { errorMessage } from "../lib/api";
import { DEMO_ACCOUNTS, DEMO_PASSWORD, useAuth } from "../lib/auth";

/** ทางเข้าของพนักงาน — แยกจากหน้าลูกค้าโดยสิ้นเชิง
 *
 * ข้อควรเข้าใจ: การแยกหน้าไม่ได้ทำให้ "ปลอดภัยขึ้น" ใครพิมพ์ /staff ก็เปิดหน้านี้ได้
 * ของจริงที่กันคือฝั่ง backend — ล็อกชั่วคราวเมื่อลองผิด 5 ครั้ง, ไม่บอกว่ารหัสพนักงาน
 * นั้นมีจริงไหม, และเขียน audit ทุกครั้งที่มีคนพยายามเข้า (ดู auth_service.login)
 *
 * ที่แยกเพราะเป็นคนละงาน: คนละชนิดของบัญชี คนละปลายทางหลังเข้าสู่ระบบ และไม่ต้อง
 * เอาตัวเลือกที่ลูกค้าไม่มีวันใช้ไปวางขวางหน้าลูกค้า
 */
export default function StaffLoginPage() {
  const auth = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  // รับเฉพาะ path ภายใน — ปล่อยให้เป็น URL เต็มจะกลายเป็น open redirect
  const raw = params.get("next") || "";
  const next = raw.startsWith("/") && !raw.startsWith("//") ? raw : "";
  const [code, setCode] = useState("");
  const [pass, setPass] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const user = await auth.login(code.trim(), pass, "staff");
      // มี next = โดนเด้งออกมาจากหน้านั้น พากลับไปที่เดิม · ไม่มีก็เข้าหน้าประจำของแต่ละบทบาท
      nav(next || (user.role === "admin" ? "/manager/sap-sync" : "/sales"), { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  if (auth.user?.role && auth.user.role !== "customer") {
    return (
      <AuthShell title="เข้าสู่ระบบอยู่แล้ว" subtitle={`${auth.user.name} · ${auth.user.staff_code}`}>
        <Link className="btn primary block" to={next || "/sales"}>{next ? "กลับไปหน้าที่ค้างไว้" : "ไปที่ตะกร้าที่กำลังดูแล"}</Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="สำหรับพนักงาน SB"
      subtitle="เข้าสู่ระบบด้วยรหัสพนักงานเพื่อใช้เครื่องมือขาย"
      footer={<>เป็นลูกค้า? <Link to="/login">เข้าสู่ระบบด้วยเบอร์โทร</Link></>}
    >
      <>
        <form onSubmit={submit} className="form">
          <label className="field">
            <span>รหัสพนักงาน</span>
            <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="เช่น SA-104" autoFocus autoCapitalize="characters" />
          </label>
          <label className="field">
            <span>รหัสผ่าน</span>
            <input type="password" value={pass} onChange={(e) => setPass(e.target.value)} placeholder="••••" autoComplete="current-password" />
          </label>
          {error && <div className="note err">{error}</div>}
          <button className="btn primary block" type="submit" disabled={busy || !code.trim() || !pass.trim()}>
            {busy ? "กำลังตรวจสอบ…" : "เข้าสู่ระบบ"}
          </button>
        </form>

        <p className="tiny muted" style={{ marginTop: 12 }}>
          <Icon name="shield" size={14} /> ลองรหัสผิดหลายครั้งติดกันระบบจะหยุดรับชั่วคราว · ทุกครั้งที่เข้าสู่ระบบมีการบันทึกไว้
        </p>

        <div className="auth-or">บัญชีทดสอบ</div>

        <div className="demo-accounts">
          {DEMO_ACCOUNTS.filter((d) => d.type === "staff").map((d) => (
            <button key={d.id} className="demo-row" onClick={() => { setCode(d.id); setPass(DEMO_PASSWORD); setError(null); }}>
              <Icon name="badge" size={20} />
              <span><b>{d.title}</b><small>{d.sub}</small></span>
            </button>
          ))}
        </div>
      </>
    </AuthShell>
  );
}
