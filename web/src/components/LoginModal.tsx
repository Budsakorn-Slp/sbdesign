import { useState, type FormEvent } from "react";
import { errorMessage } from "../lib/api";
import { DEMO_ACCOUNTS, useAuth } from "../lib/auth";
import Icon from "./Icon";

type Tab = "customer" | "staff";
type Mode = "password" | "otp" | "register";

export default function LoginModal() {
  const auth = useAuth();
  const [tab, setTab] = useState<Tab>("customer");
  const [mode, setMode] = useState<Mode>("password");
  const [id, setId] = useState("");
  const [pass, setPass] = useState("");
  const [name, setName] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [otpHint, setOtpHint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!auth.loginOpen) return null;

  const reset = () => {
    setError(null);
    setOtpHint(null);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (tab === "customer" && mode === "otp") {
        if (!otpHint) {
          const r = await auth.otpRequest(id);
          setOtpHint(r.debug_code ? `ส่ง OTP แล้ว (โหมดทดสอบ: รหัส ${r.debug_code})` : "ส่ง OTP ไปที่มือถือแล้ว");
        } else {
          await auth.otpVerify(id, otpCode, name || undefined);
        }
      } else if (tab === "customer" && mode === "register") {
        await auth.register(id, pass, name);
      } else {
        if (!id.trim() || !pass.trim()) throw new Error("กรอกข้อมูลให้ครบทั้ง 2 ช่อง (บัญชีทดสอบกดปุ่มด้านล่างได้)");
        await auth.login(id, pass, tab);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const idLabel = tab === "staff" ? "รหัสพนักงาน" : mode === "otp" || mode === "register" ? "เบอร์โทรศัพท์" : "เบอร์โทร / อีเมล / เลขสมาชิก";
  const idPlaceholder = tab === "staff" ? "เช่น SA-104" : "เช่น 089-234-4471";

  return (
    <div className="modal-backdrop" onClick={auth.closeLogin}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{tab === "staff" ? "เข้าสู่ระบบพนักงาน" : mode === "register" ? "ลงทะเบียนลูกค้าใหม่" : "เข้าสู่ระบบลูกค้า"}</h2>
          <button className="icon-btn" onClick={auth.closeLogin} aria-label="ปิด">
            <Icon name="close" />
          </button>
        </div>

        <div className="seg">
          {(["customer", "staff"] as Tab[]).map((t) => (
            <button key={t} className={"seg-btn" + (tab === t ? " on" : "")} onClick={() => { setTab(t); setMode("password"); reset(); }}>
              {t === "customer" ? "ลูกค้า" : "พนักงานขาย"}
            </button>
          ))}
        </div>

        {tab === "customer" && (
          <div className="tabs-inline">
            {(["password", "otp", "register"] as Mode[]).map((m) => (
              <button key={m} className={"link-btn" + (mode === m ? " on" : "")} onClick={() => { setMode(m); reset(); }}>
                {m === "password" ? "รหัสผ่าน" : m === "otp" ? "OTP" : "ลงทะเบียน"}
              </button>
            ))}
          </div>
        )}

        <form onSubmit={submit} className="form">
          <label className="field">
            <span>{idLabel}</span>
            <input value={id} onChange={(e) => setId(e.target.value)} placeholder={idPlaceholder} autoFocus />
          </label>
          {tab === "customer" && (mode === "register" || (mode === "otp" && otpHint)) && (
            <label className="field">
              <span>ชื่อ-นามสกุล{mode === "otp" ? " (ถ้ายังไม่เคยสมัคร)" : ""}</span>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="เช่น ณภัทร พงษ์ศรี" />
            </label>
          )}
          {!(tab === "customer" && mode === "otp") && (
            <label className="field">
              <span>รหัสผ่าน</span>
              <input type="password" value={pass} onChange={(e) => setPass(e.target.value)} placeholder="••••" />
            </label>
          )}
          {tab === "customer" && mode === "otp" && otpHint && (
            <label className="field">
              <span>รหัส OTP 6 หลัก</span>
              <input value={otpCode} onChange={(e) => setOtpCode(e.target.value)} placeholder="000000" inputMode="numeric" />
            </label>
          )}
          {otpHint && <div className="note ok">{otpHint}</div>}
          {error && <div className="note err">{error}</div>}
          <button className="btn primary block" type="submit" disabled={busy}>
            {busy ? "กำลังตรวจสอบ…" : tab === "customer" && mode === "otp" && !otpHint ? "ขอรหัส OTP" : mode === "register" ? "ลงทะเบียน" : "เข้าสู่ระบบ"}
          </button>
        </form>

        <div className="demo-accounts">
          <div className="demo-head">บัญชีทดสอบ (กดเพื่อกรอกอัตโนมัติ)</div>
          {DEMO_ACCOUNTS.map((d) => (
            <button
              key={d.id}
              className="demo-row"
              onClick={() => { setTab(d.type); setMode("password"); setId(d.id); setPass("1234"); reset(); }}
            >
              <Icon name={d.type === "staff" ? "badge" : "person"} size={20} />
              <span>
                <b>{d.title}</b>
                <small>{d.sub}</small>
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
