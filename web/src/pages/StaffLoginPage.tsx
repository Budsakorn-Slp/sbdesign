import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import AuthShell from "../components/AuthShell";
import Icon from "../components/Icon";
import { errorMessage } from "../lib/api";
import { DEMO_ACCOUNTS, DEMO_PASSWORD, useAuth } from "../lib/auth";
import { usePublicConfig } from "../lib/publicConfig";
import { redirectFor } from "../lib/routes";

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
  const cfg = usePublicConfig();
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
      const home = user.role === "admin" ? "/manager/sap-sync" : "/sales";
      // มี next = โดนเด้งออกมาจากหน้านั้น พากลับไปที่เดิม · ไม่มีก็เข้าหน้าประจำของแต่ละบทบาท
      //
      // แต่ต้องเช็คก่อนว่าบัญชีที่เพิ่งเข้ามา "มีสิทธิ์" เข้าหน้านั้นจริงไหม
      // ไม่งั้นพนักงานขายที่ล็อกอินเพื่อไปหน้าของผู้จัดการจะโดนเด้งกลับมาที่นี่ แล้ววนไม่จบ
      nav(next && !redirectFor(next, user.role) ? next : home, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  if (auth.user?.role && auth.user.role !== "customer") {
    const home = auth.user.role === "admin" ? "/manager/sap-sync" : "/sales";
    // สิทธิ์ไม่ถึงหน้าปลายทาง = กดปุ่มไปก็โดนเด้งกลับมาที่นี่อีก วนไม่จบและดูเหมือนปุ่มเสีย
    // บอกตรงๆ ว่าบัญชีนี้เข้าไม่ได้ แล้วให้ทางออกสองทาง: ไปหน้าที่ใช้ได้ หรือสลับบัญชี
    const denied = !!next && !!redirectFor(next, auth.user.role);
    return (
      <AuthShell
        title={denied ? "บัญชีนี้เข้าหน้านั้นไม่ได้" : "เข้าสู่ระบบอยู่แล้ว"}
        subtitle={`${auth.user.name} · ${auth.user.staff_code}`}
      >
        {denied && (
          <p className="note tiny" style={{ marginBottom: 10 }}>
            หน้า <b>{next}</b> เปิดให้เฉพาะผู้จัดการและแอดมิน — เข้าด้วยบัญชีที่มีสิทธิ์ถึงจะเข้าได้
          </p>
        )}
        <Link className="btn primary block" to={denied || !next ? home : next}>
          {denied ? "ไปหน้าเครื่องมือขาย" : next ? "กลับไปหน้าที่ค้างไว้" : "ไปที่ตะกร้าที่กำลังดูแล"}
        </Link>
        <button type="button" className="link-btn small" style={{ marginTop: 10 }}
                onClick={() => { void auth.logout(); }}>
          เข้าสู่ระบบด้วยบัญชีอื่น
        </button>
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

        {/* รายชื่อบัญชีทดสอบพร้อมรหัสผ่าน — มีไว้ให้ dev กดเร็วๆ เท่านั้น
            ห้ามโผล่บนของจริง ไม่งั้นเท่ากับแปะรหัสเข้าระบบหลังร้านไว้หน้าเว็บ */}
        {cfg && !cfg.invite_only && (
          <>
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
        )}
      </>
    </AuthShell>
  );
}
