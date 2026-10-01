import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiPost, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { TokenPair, User } from "../lib/types";
import Icon from "./Icon";
import OtpInput from "./OtpInput";

const RESEND_SECONDS = 60; // ต้องตรงกับ OTP_RESEND_COOLDOWN_SECONDS ฝั่ง backend

/** คำลัดเปิดหน้าเข้าสู่ระบบพนักงาน — พิมพ์ในช่องแรกแล้วกดเข้าสู่ระบบ จะเด้งไป /staff
 *
 * ไม่ใช่รหัสผ่านและไม่ได้กันใคร: ค่านี้อยู่ในไฟล์ JS ที่ส่งให้ทุกคน เปิด DevTools ก็อ่านได้
 * ยอมรับได้เพราะถึงรู้ก็แค่ไปโผล่หน้า /staff ซึ่งพิมพ์ URL ตรงๆ ก็เข้าได้อยู่แล้ว
 * ประโยชน์จริงคือตอนบุ๊กมาร์กใช้ไม่ได้ (แท็บเล็ตกลางโชว์รูม เครื่องใหม่ เบราว์เซอร์คนอื่น)
 * — จำคำเดียวง่ายกว่าจำ URL เต็ม · เปลี่ยนคำได้ที่ VITE_STAFF_DOOR ใน web/.env
 */
/** เบอร์มือถือไทย = ตัวเลข 10 หลัก
 *
 * กรองตั้งแต่ตอนพิมพ์ ไม่ใช่ไปเตือนหลังกดส่ง — คนวางเบอร์จากสมุดโทรศัพท์มักติดขีดหรือเว้นวรรค
 * มาด้วย ("094-916-4600") ตัดให้เงียบๆ ดีกว่าขึ้น error ให้เขาไปลบเอง
 *
 * ไม่ใช้กับโหมดรหัสผ่าน เพราะช่องเดียวกันนั้นรับอีเมลและคำลัดพนักงานด้วย
 */
const PHONE_LEN = 10;
const onlyDigits = (v: string) => v.replace(/\D/g, "").slice(0, PHONE_LEN);

const STAFF_DOOR = (import.meta.env.VITE_STAFF_DOOR || "SA-Sale").trim().toLowerCase();

/** เข้าสู่ระบบลูกค้า — 3 ทางในฟอร์มเดียว
 *
 *   password : เบอร์/อีเมล + รหัสผ่าน — ทางปกติของคนที่ตั้งรหัสไว้แล้ว
 *   otp      : เบอร์ + รหัส 6 หลัก · เบอร์ที่ยังไม่มีบัญชีจะถูกสร้างให้เลย
 *              "สมัคร" กับ "เข้าสู่ระบบ" จึงเป็นทางเดียวกัน ไม่ต้องมีแท็บลงทะเบียนแยก
 *   register : สมัครสมาชิกใหม่ — ทางเดียวกับ otp ทุกประการ ต่างแค่ถ้อยคำ
 *              (ฝั่ง backend สร้างบัญชีให้เองเมื่อยืนยัน OTP ของเบอร์ที่ยังไม่มีในระบบ)
 *              แยกเป็นปุ่มของตัวเองเพราะลูกค้าใหม่มองหาคำว่า "สมัครสมาชิก" ไม่ใช่ "เข้าด้วย OTP"
 *
 * ไม่มีช่องชื่อในฟอร์มนี้ทั้งสองโหมด — ตอนกรอกเรายังไม่รู้ว่าเบอร์นี้มีบัตรสมาชิก SB อยู่ไหม
 * (backend ตั้งใจไม่บอกก่อนยืนยัน ไม่งั้นกลายเป็นเครื่องมือไล่เช็คว่าเบอร์ไหนเป็นลูกค้า)
 * พอยืนยัน OTP เสร็จถึงจะรู้: มีบัตร → ดึงชื่อจากทะเบียนให้เลย · ไม่มีบัตร → หน้าตั้งค่าบัญชี
 * บังคับกรอกชื่อ · ลูกค้าจึงไม่เจอช่องที่ "ใส่ก็ได้ไม่ใส่ก็ได้" ระบบตัดสินให้เองว่าต้องถามไหม
 *   forgot   : ลืมรหัสผ่าน → ยืนยัน OTP → ตั้งรหัสใหม่ แล้วเข้าระบบให้เลย
 *
 * ทั้งสามทางจบด้วย onDone(user) เหมือนกัน ผู้เรียกจึงพาไปขั้นผูกเลขสมาชิกต่อได้ทางเดียว
 */
type Mode = "password" | "otp" | "register" | "forgot";

export default function CustomerLogin({ onDone, presetPhone, allowSignup = true, allowOtp = true }:
  { onDone?: (user: User, mode: Mode) => void; presetPhone?: string;
    /** ช่วงทดสอบก่อนเปิดจริงตั้งเป็น false — ซ่อนทางสมัครสมาชิก
     *  (หลังบ้านกันไว้อีกชั้นอยู่แล้ว ตรงนี้แค่ไม่ให้ชวนกดแล้วเจอ error) */
    allowSignup?: boolean;
    /** false = ระบบส่ง OTP ไม่ได้ (ยังไม่ได้ต่อ SMS) — ซ่อนทั้ง "เข้าด้วย OTP" และ "ลืมรหัสผ่าน"
     *  เพราะทั้งสองทางจบที่หน้ากรอกรหัสที่ไม่มีวันส่งมาถึง */
    allowOtp?: boolean }) {
  const auth = useAuth();
  const nav = useNavigate();
  const [mode, setMode] = useState<Mode>("password");
  const [id, setId] = useState(""); // เบอร์ (หรืออีเมลเฉพาะโหมดรหัสผ่าน)
  const [pass, setPass] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [wait, setWait] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // รหัส OTP ที่ยิงอัตโนมัติไปแล้ว — กันยิงซ้ำวนลูปตอนรหัสผิด (ดู useEffect ข้างล่าง)
  const tried = useRef<string | null>(null);

  const clear = () => {
    setSent(null);
    setCode("");
    tried.current = null; // เปลี่ยนเบอร์/เปลี่ยนโหมด = เริ่มนับใหม่ ไม่งั้นรหัสเดิมยิงอัตโนมัติไม่ได้
    setPass("");
    setError(null);
  };

  // ปุ่มบัญชีทดสอบข้างนอกส่งเบอร์เข้ามา — เติมให้แล้วถอยกลับไปขั้นแรกเสมอ
  useEffect(() => {
    if (presetPhone) {
      setId(mode === "password" ? presetPhone : onlyDigits(presetPhone));
      clear();
    }
  }, [presetPhone]);

  useEffect(() => {
    if (wait <= 0) return;
    const t = setTimeout(() => setWait((n) => n - 1), 1000);
    return () => clearTimeout(t);
  }, [wait]);

  const askOtp = async (forgot: boolean) => {
    const r = forgot
      ? await apiPost<{ debug_code?: string }>("/auth/password/forgot", { phone: id })
      : await auth.otpRequest(id);
    // debug_code มาเฉพาะตอน OTP_DEBUG เปิด (dev/เทส) — โปรดักชันจะไม่มีค่านี้
    setSent(r.debug_code ? `ส่งรหัสแล้ว · โหมดทดสอบ: ${r.debug_code}` : "ส่งรหัส 6 หลักไปที่มือถือแล้ว");
    setWait(RESEND_SECONDS);
  };

  const isStaffDoor = id.trim().toLowerCase() === STAFF_DOOR;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    // คำลัด: เปิดหน้าพนักงานแล้วจบ — ไม่ยิง API เลย จึงไม่ถูกนับเป็นการล็อกอินที่ล้มเหลว
    if (isStaffDoor) {
      auth.closeLogin(); // เผื่อกดมาจากกล่องที่เปิดทับหน้าเดิม ต้องปิดก่อนเปลี่ยนหน้า
      nav("/staff");
      return;
    }
    await run();
  };

  const run = async () => {
    setError(null);
    setBusy(true);
    try {
      if (mode === "password") {
        onDone?.(await auth.login(id.trim(), pass, "customer"), mode);
      } else if (!sent) {
        await askOtp(mode === "forgot");
      } else if (mode === "otp" || mode === "register") {
        onDone?.(await auth.otpVerify(id, code), mode);
      } else {
        const t = await apiPost<TokenPair>("/auth/password/reset", { phone: id, code, new_password: pass });
        await auth.adopt(t); // ตั้งรหัสใหม่แล้วเข้าระบบให้เลย ไม่ต้องกรอกซ้ำอีกรอบ
        onDone?.(t.user, mode);
      }
    } catch (err) {
      setError(errorMessage(err));
      // รหัสผิด: ล้างช่องให้พิมพ์ใหม่ได้เลย (ไม่ต้องลบทีละหลัก) และปลดล็อกการยิงอัตโนมัติ
      if (mode !== "forgot" && sent) {
        setCode("");
        tried.current = null;
      }
    } finally {
      setBusy(false);
    }
  };

  /** กรอกครบ 6 หลักแล้วยิงเลย ไม่ต้องกดปุ่มยืนยัน
   *
   * รหัส OTP มีความยาวตายตัว พอครบ 6 หลักก็ไม่เหลืออะไรให้ลูกค้าตัดสินใจอีกแล้ว — การให้กดปุ่ม
   * ต่ออีกทีคือขั้นตอนที่ไม่ได้เพิ่มอะไร (แอปธนาคาร/แอปใหญ่ๆ ทำแบบนี้กันหมด)
   *
   * ยกเว้นโหมด forgot ที่ยังต้องพิมพ์รหัสผ่านใหม่ต่อ — ยิงตอนเขายังพิมพ์ไม่เสร็จจะกลายเป็น
   * แย่งฟอร์มไปเอง · ส่วน otp/register ไม่มีช่องอื่นให้กรอกแล้ว ครบ 6 หลักคือจบ
   *
   * tried จำรหัสที่ยิงไปแล้ว เพื่อไม่ให้ยิงซ้ำวนไปเรื่อยๆ ตอนรหัสผิด (ค่าที่ผิดยังอยู่ในช่อง
   * ครบ 6 หลักเหมือนเดิม) — ลบหนึ่งหลักแล้วพิมพ์ใหม่ถึงจะยิงอีกครั้ง
   */
  useEffect(() => {
    if ((mode !== "otp" && mode !== "register") || !sent || busy) return;
    if (code.length !== 6 || tried.current === code) return;
    tried.current = code;
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run อ่าน state ล่าสุดผ่าน closure ที่ render ใหม่ทุกครั้งอยู่แล้ว
  }, [code, mode, sent, busy]);

  const go = (m: Mode) => {
    setMode(m);
    // สลับมาจากโหมดรหัสผ่านที่พิมพ์อีเมลค้างไว้ — ช่องนี้รับได้แค่เบอร์แล้ว
    if (m !== "password") setId(onlyDigits(id));
    clear();
  };

  // ป้ายบอกว่ากำลังทำอะไรอยู่ ขั้นไหน — เฉพาะโหมดที่มี 2 ขั้น ไม่งั้นหน้าตาเหมือนโหมด OTP
  // จนแยกไม่ออกว่ากดอะไรมา (โหมด password/otp จบในขั้นเดียว ไม่ต้องมีป้าย)
  const step: { title: string; hint: string } | null =
    mode === "register"
      ? sent
        ? { title: "สมัครสมาชิก · ขั้นที่ 2 จาก 2", hint: "ใส่รหัสที่ได้รับ — ยืนยันแล้วระบบจะเช็คบัตรสมาชิก SB จากเบอร์นี้ให้เอง" }
        : { title: "สมัครสมาชิก · ขั้นที่ 1 จาก 2", hint: "ยืนยันเบอร์โทรก่อน เพื่อใช้สะสมแต้มและผูกบัตรสมาชิกเดิมที่มีอยู่ได้" }
      : mode === "forgot"
        ? sent
          ? { title: "ตั้งรหัสผ่านใหม่ · ขั้นที่ 2 จาก 2", hint: "ใส่รหัสที่ได้รับ แล้วตั้งรหัสผ่านใหม่" }
          : { title: "ตั้งรหัสผ่านใหม่ · ขั้นที่ 1 จาก 2", hint: "ใส่เบอร์ที่ใช้สมัครไว้ เราจะส่งรหัสไปยืนยันว่าเป็นเจ้าของเบอร์จริง" }
        : null;

  const cta = busy
    ? "กำลังตรวจสอบ…"
    : mode === "password"
      ? "เข้าสู่ระบบ"
      : !sent
        ? "ขอรหัส OTP"
        : mode === "forgot"
          ? "ตั้งรหัสผ่านใหม่"
          : mode === "register"
            ? "ยืนยันและสมัครสมาชิก"
            : "ยืนยันรหัส";

  const ready =
    isStaffDoor
      ? true
      : mode === "password"
      ? !!id.trim() && !!pass.trim()
      : !sent
        ? id.length === PHONE_LEN
        : code.trim().length >= 4
          && (mode !== "forgot" || pass.trim().length >= 4);

  return (
    <form onSubmit={submit} className="form" autoComplete="on">
      {step && (
        <div className="auth-step">
          <b>{step.title}</b>
          <small>{step.hint}</small>
        </div>
      )}

      {!sent ? (
        <label className="field">
          <span>{mode === "password" ? "เบอร์โทร หรือ อีเมล" : "เบอร์โทรศัพท์"}</span>
          <input
            value={id}
            onChange={(e) => setId(mode === "password" ? e.target.value : onlyDigits(e.target.value))}
            placeholder="เบอร์โทรศัพท์ 10 หลัก"
            inputMode={mode === "password" ? "text" : "numeric"}
            maxLength={mode === "password" ? undefined : PHONE_LEN}
            autoComplete="tel"
            autoFocus
          />
        </label>
      ) : (
        <>
          {/* ปุ่มเปลี่ยนเบอร์อยู่บนสุดของขั้นนี้ — คนที่พิมพ์เบอร์ผิดจะมองหาตรงนี้ก่อน
              ไม่ใช่ไปหาท้ายฟอร์มหลังกรอกรหัสไปแล้ว */}
          <button type="button" className="link-btn small otp-back" onClick={clear}>
            <Icon name="chevron_left" size={18} /> เปลี่ยนเบอร์
          </button>
          <p className="otp-sent">
            ส่งรหัส OTP 6 หลักไปที่ <b>{id}</b> แล้ว กรุณากรอกรหัสเพื่อยืนยัน
          </p>
          <OtpInput value={code} onChange={setCode} disabled={busy} autoFocus />
        </>
      )}

      {/* โหมดรหัสผ่าน = ใส่รหัสเดิม · โหมดลืมรหัส = ตั้งรหัสใหม่ (โผล่หลังส่ง OTP แล้ว) */}
      {(mode === "password" || (mode === "forgot" && sent)) && (
        <label className="field">
          <span>{mode === "forgot" ? "ตั้งรหัสผ่านใหม่" : "รหัสผ่าน"}</span>
          <input
            type="password"
            value={pass}
            onChange={(e) => setPass(e.target.value)}
            placeholder="••••••"
            autoComplete={mode === "forgot" ? "new-password" : "current-password"}
          />
        </label>
      )}

      {sent && <div className="note ok">{sent}</div>}
      {error && <div className="note err">{error}</div>}

      <button className="btn primary block" type="submit" disabled={busy || !ready}>{cta}</button>

      {sent && (
        <p className="otp-resend">
          ยังไม่ได้รับรหัส?{" "}
          <button
            type="button"
            className="link-btn small"
            onClick={() => {
              // รหัสเดิมใช้ไม่ได้แล้วหลังขอใหม่ — ล้างช่องไว้รอรหัสใหม่
              setCode("");
              tried.current = null;
              void askOtp(mode === "forgot").catch((err) => setError(errorMessage(err)));
            }}
            disabled={busy || wait > 0}
          >
            ส่งอีกครั้ง
          </button>
          {wait > 0 && <span className="muted"> ({wait}s)</span>}
        </p>
      )}

      {/* ปุ่มกลับมีทุกขั้น — เดิมพอส่ง OTP แล้วปุ่มหาย คนที่กดผิดโหมดจะติดอยู่ตรงนั้น */}
      {mode !== "password" && (
        <button type="button" className="link-btn small block" onClick={() => go("password")}>
          <Icon name="arrow_back" size={14} /> กลับไปหน้าเข้าสู่ระบบ
        </button>
      )}

      {!sent && (
        <>
          {mode === "password" && allowOtp && (
            <div className="auth-links">
              <button type="button" className="link-btn small" onClick={() => go("otp")}>เข้าด้วยรหัส OTP</button>
              <button type="button" className="link-btn small" onClick={() => go("forgot")}>ลืมรหัสผ่าน?</button>
            </div>
          )}
          {/* ยังต่อ SMS ไม่ได้ = เข้าได้ทางเดียวคือรหัสผ่าน บอกให้ชัดดีกว่าปล่อยให้งง */}
          {mode === "password" && !allowOtp && (
            <div className="note tiny" style={{ marginTop: 8 }}>
              ช่วงทดสอบเข้าด้วยรหัสผ่านเท่านั้น — ลืมรหัสติดต่อผู้ดูแลระบบ
            </div>
          )}

          {/* ลูกค้าใหม่มองหาคำว่า "สมัครสมาชิก" — ของเดิมมีแต่ทาง OTP ซึ่งสมัครให้อยู่แล้ว
              แต่ไม่มีอะไรบอก คนเลยไม่รู้ว่าต้องกดตรงไหน */}
          {allowSignup && mode !== "register" ? (
            <>
              <div className="auth-or">ยังไม่มีบัญชี?</div>
              <button type="button" className="btn block" onClick={() => go("register")}>
                <Icon name="person_add" size={18} /> สมัครสมาชิกใหม่
              </button>
            </>
          ) : null}
        </>
      )}
    </form>
  );
}
