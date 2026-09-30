import { useEffect, useState } from "react";
import { apiDelete, apiGet, apiPatch, apiPost, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { MemberCard, MemberLinkStart } from "../lib/types";
import Icon from "./Icon";

/** ผูกบัญชีเว็บเข้ากับเลขสมาชิก SB
 *
 * ทางหลักคือ "ระบบหาให้เอง" — เบอร์ที่เพิ่งยืนยัน OTP ไปคือหลักฐานอยู่ในตัวแล้ว เอาไปค้น
 * ทะเบียนสมาชิกได้เลย ลูกค้าแค่กดยืนยันว่าใช่ ไม่ต้องพิมพ์เลขสมาชิกที่จำไม่ได้อยู่แล้ว
 *
 * ทางรองคือพิมพ์เลขเอง สำหรับคนที่เปลี่ยนเบอร์ — ทางนี้ต้องยืนยัน OTP ที่ "เบอร์ในทะเบียน"
 * ก่อนเสมอ (ฝั่ง backend บังคับ ดู member_service) เพราะเลขสมาชิกพิมพ์อยู่บนใบเสร็จทุกใบ
 * ใช้เป็นหลักฐานยืนยันตัวตนไม่ได้
 */
/** หัวข้อด้านนอกต้องเปลี่ยนตามช่วงที่ MemberLink กำลังแสดง — ไม่งั้นได้หัวข้อ
 * "เชื่อมบัญชีสมาชิก" คร่อมฟอร์มที่ถามชื่อ/อีเมล/รหัสผ่าน ซึ่งคนละเรื่องกัน */
export type Phase = "member" | "profile";
export const SHELL: Record<Phase, { title: string; subtitle: string }> = {
  member: { title: "เชื่อมบัญชีสมาชิก", subtitle: "สะสมแต้มและดูประวัติการซื้อจากหน้าร้านได้ในที่เดียว" },
  profile: { title: "อีกขั้นเดียว", subtitle: "กรอกข้อมูลบัญชีให้ครบ แล้วเริ่มช้อปได้เลย" },
};

type Step = "loading" | "found" | "none" | "manual" | "otp" | "done" | "profile";

export default function MemberLink({ onDone, compact, onPhase }: {
  onDone?: () => void;
  compact?: boolean;
  /** บอกผู้เรียกว่าตอนนี้อยู่ช่วงไหน เพื่อให้หัวข้อด้านนอก (AuthShell) ตรงกับสิ่งที่เห็นอยู่ */
  onPhase?: (phase: "member" | "profile") => void;
}) {
  const auth = useAuth();
  const [step, setStep] = useState<Step>("loading");
  const [card, setCard] = useState<MemberCard | null>(null);
  const [manualNo, setManualNo] = useState("");
  const [otp, setOtp] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [pass, setPass] = useState("");

  // ชื่อชั่วคราวที่ backend ตั้งให้ตอนเข้าระบบด้วย OTP ครั้งแรก ("ลูกค้า 4600")
  // ไม่เอามาเติมในช่อง เพราะเป็นค่าที่ระบบตั้งเอง ไม่ใช่ชื่อที่ลูกค้าพิมพ์
  const u = auth.user;
  const placeholderName = !!u && !!u.phone && u.name.trim() === `ลูกค้า ${u.phone.slice(-4)}`;

  // เติมค่าที่มีอยู่แล้วให้ (เช่น คนที่เคยข้ามไปแล้วกลับมาแก้) — ยกเว้นชื่อชั่วคราว
  useEffect(() => {
    if (u && !placeholderName) setName((n) => n || u.name);
    if (u?.email) setEmail((e) => e || u.email || "");
  }, [u, placeholderName]);

  /** บันทึกข้อมูลบัญชี
   *
   * ส่ง onboarded ไปด้วยเสมอ — ถ้าไม่ทำเครื่องหมายไว้ คนที่ไม่มีบัตรสมาชิกจะเจอหน้านี้ทุกครั้ง
   * ที่ล็อกอิน เพราะเงื่อนไข "ยังไม่มีเลขสมาชิก" เป็นจริงของเขาตลอดไป
   */
  const saveProfile = () =>
    run(async () => {
      const body: Record<string, string | boolean> = { onboarded: true };
      if (name.trim()) body.name = name.trim();
      if (email.trim()) body.email = email.trim();
      if (pass) body.password = pass;
      await apiPatch("/me", body);
      await auth.refreshMe();
      onDone?.();
    });

  useEffect(() => {
    if (step === "loading") return;
    onPhase?.(step === "none" || step === "profile" ? "profile" : "member");
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onPhase เป็น callback ของผู้เรียก ไม่ควรเป็นเงื่อนไขยิงซ้ำ
  }, [step]);

  useEffect(() => {
    let alive = true;
    apiGet<MemberCard[]>("/me/member/candidates")
      .then((rows) => {
        if (!alive) return;
        setCard(rows[0] || null);
        setStep(rows.length ? "found" : "none");
      })
      .catch(() => alive && setStep("none")); // หาไม่เจอ/ระบบสมาชิกล่ม — ข้ามไปก่อนได้ ไม่ใช่ทางตัน
    return () => {
      alive = false;
    };
  }, []);

  // eslint-disable-next-line @typescript-eslint/no-use-before-define -- run ถูกเรียกใน saveProfile ข้างบน
  async function run(fn: () => Promise<void>) {
    setError(null);
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const link = (sap_customer_no: string, otp_code?: string) =>
    run(async () => {
      const done = await apiPost<{ name: string; points: number }>("/me/member/link", { sap_customer_no, otp_code });
      await auth.refreshMe(); // แต้ม/เลขสมาชิกเปลี่ยนแล้ว ให้หัวเว็บกับหน้าอื่นเห็นตรงกัน
      setCard((c) => (c ? { ...c, name: done.name, points: done.points } : c));
      setStep("done");
    });

  const lookup = () =>
    run(async () => {
      const r = await apiPost<MemberLinkStart>("/me/member/lookup", { sap_customer_no: manualNo.trim() });
      setCard(r.member);
      if (!r.requires_otp) return link(r.sap_customer_no);
      // เบอร์ในทะเบียนไม่ตรงกับเบอร์ที่ยืนยันไว้ → ต้องพิสูจน์ว่าถือเบอร์นั้นจริงก่อน
      const sent = await apiPost<{ phone: string }>("/me/member/otp", { sap_customer_no: r.sap_customer_no });
      setSentTo(sent.phone);
      setStep("otp");
    });

  const unlink = () =>
    run(async () => {
      await apiDelete("/me/member/link");
      await auth.refreshMe();
      setCard(null);
      setStep("none");
    });

  if (step === "loading") return <div className="ph" style={{ height: compact ? 90 : 140, borderRadius: 12 }} />;

  // ---------- ผูกสำเร็จ ----------
  if (step === "done" && card) {
    return (
      <div className="member-box ok">
        <span className="member-ic"><Icon name="verified" size={22} /></span>
        <div className="grow">
          <b>ผูกบัญชีสมาชิกแล้ว</b>
          <small>{card.name} · {card.points.toLocaleString()} พ้อยท์ · เลขสมาชิก {card.sap_customer_no}</small>
        </div>
        {onDone ? (
          <button className="btn primary sm" onClick={onDone}>ไปต่อ</button>
        ) : (
          <button className="link-btn small" onClick={unlink} disabled={busy}>ยกเลิกการผูก</button>
        )}
      </div>
    );
  }

  // ---------- เจอแล้ว รอยืนยัน ----------
  if (step === "found" && card) {
    return (
      <div className="member-box">
        <div className="member-head">
          <span className="member-ic"><Icon name="card_membership" size={22} /></span>
          <div>
            <b>เจอบัญชีสมาชิกของคุณ</b>
            <small>เบอร์ที่ยืนยันแล้วตรงกับสมาชิกรายนี้</small>
          </div>
        </div>
        <div className="member-card">
          <div className="row between">
            <b>{card.name}</b>
            <span className="chip brand">{card.points.toLocaleString()} พ้อยท์</span>
          </div>
          <small className="muted">เลขสมาชิก {card.sap_customer_no} · {card.phone_masked}</small>
        </div>
        {error && <div className="note err">{error}</div>}
        <div className="member-actions">
          <button className="btn primary grow" onClick={() => link(card.sap_customer_no)} disabled={busy}>
            {busy ? "กำลังผูก…" : "ใช่ ผูกบัญชีนี้"}
          </button>
          {/* เป็นสมาชิกอยู่ก็ไม่ผูกได้ — บางคนไม่อยากให้ประวัติหน้าร้านมาปนกับบัญชีออนไลน์
              ไม่ผูก = ไม่มีชื่อ/อีเมลจากทะเบียนให้ใช้ จึงต้องไปกรอกเองที่ขั้นถัดไป */}
          {onDone && <button className="btn grow" onClick={() => setStep("profile")} disabled={busy}>ไม่ผูก ขอบคุณ</button>}
        </div>
        <p className="tiny muted">ผูกแล้วแต้มสะสมและประวัติการซื้อจากหน้าร้านจะมาอยู่ในบัญชีนี้ · ยกเลิกภายหลังได้</p>
      </div>
    );
  }

  // ---------- กรอก OTP ที่ส่งไปเบอร์ในทะเบียน ----------
  if (step === "otp") {
    return (
      <div className="member-box">
        <div className="member-head">
          <span className="member-ic"><Icon name="sms" size={22} /></span>
          <div>
            <b>ยืนยันว่าเป็นเจ้าของบัญชีสมาชิก</b>
            <small>ส่งรหัสไปที่เบอร์ที่ผูกกับสมาชิกรายนี้ {sentTo}</small>
          </div>
        </div>
        <label className="field">
          <span>รหัส 6 หลัก</span>
          <input value={otp} onChange={(e) => setOtp(e.target.value)} placeholder="000000" inputMode="numeric" maxLength={6} autoFocus />
        </label>
        {error && <div className="note err">{error}</div>}
        <div className="member-actions">
          <button className="btn primary grow" onClick={() => link(manualNo.trim(), otp)} disabled={busy || otp.trim().length < 4}>
            {busy ? "กำลังตรวจสอบ…" : "ยืนยันและผูกบัญชี"}
          </button>
          <button className="btn grow" onClick={() => { setStep("manual"); setOtp(""); setError(null); }} disabled={busy}>ย้อนกลับ</button>
        </div>
        <p className="tiny muted">ไม่ได้ถือเบอร์นั้นแล้ว? ติดต่อพนักงานที่สาขาเพื่อยืนยันตัวตนและแก้เบอร์ในระบบ</p>
      </div>
    );
  }

  // ---------- พิมพ์เลขสมาชิกเอง ----------
  if (step === "manual") {
    return (
      <div className="member-box">
        <div className="member-head">
          <span className="member-ic"><Icon name="badge" size={22} /></span>
          <div>
            <b>กรอกเลขสมาชิก</b>
            <small>ดูได้จากใบเสร็จ หรือบัตรสมาชิก SB</small>
          </div>
        </div>
        <label className="field">
          <span>เลขสมาชิก</span>
          <input value={manualNo} onChange={(e) => setManualNo(e.target.value)} placeholder="เช่น 1100440205" autoFocus />
        </label>
        {error && <div className="note err">{error}</div>}
        <div className="member-actions">
          <button className="btn primary grow" onClick={lookup} disabled={busy || !manualNo.trim()}>
            {busy ? "กำลังตรวจสอบ…" : "ตรวจสอบเลขสมาชิก"}
          </button>
          <button className="btn grow" onClick={() => { setStep("none"); setError(null); }} disabled={busy}>ย้อนกลับ</button>
        </div>
      </div>
    );
  }

  // ---------- ขั้นสุดท้าย: ไม่มีบัตรสมาชิก หรือเลือกไม่ผูก ----------
  //
  // ไม่มีทะเบียนสมาชิกให้ดึงข้อมูลมาใช้ จึงต้องกรอกเอง และบังคับทั้งสามช่อง:
  // ชื่อต้องขึ้นหัวใบเสนอราคา/ใบเสร็จ · อีเมล+รหัสผ่านไว้เข้าสู่ระบบครั้งหน้า
  // ไม่มีปุ่มข้าม เพราะข้อมูลชุดนี้ระบบต้องใช้จริง ไม่ใช่ของแถม — คนที่ไม่อยากจำอีเมล/รหัส
  // ยังเข้าด้วยเบอร์+OTP ได้ตลอดอยู่แล้ว จึงไม่ได้ปิดทางใคร
  //
  // หน้าบัญชี (ไม่มี onDone) ไม่บังคับ — เข้ามาแก้ข้อมูลทีละช่องได้ตามปกติ
  const forced = !!onDone;
  const needPass = !u?.has_password;
  const incomplete = !name.trim() || !email.trim() || (needPass && pass.length < 8);

  return (
    <div className="member-box">
      <div className="member-head">
        <span className="member-ic"><Icon name="person_add" size={22} /></span>
        <div>
          {forced && <small className="member-step">ขั้นที่ 3 จาก 3</small>}
          <b>กรอกข้อมูลบัญชี</b>
          <small>ชื่อใช้ขึ้นหัวใบเสร็จ · อีเมลกับรหัสผ่านไว้เข้าสู่ระบบครั้งหน้า</small>
        </div>
      </div>

      <label className="field">
        <span>ชื่อ-นามสกุล</span>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="เช่น ณภัทร พงษ์ศรี" autoFocus={step === "profile"} />
      </label>
      <label className="field">
        <span>อีเมล</span>
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" type="email" inputMode="email" autoComplete="email" />
      </label>
      {/* ตั้งรหัสไว้แล้วซ่อนช่องนี้ — การ "เปลี่ยน" รหัสต้องไปทางลืมรหัสผ่าน (ยืนยัน OTP) */}
      {needPass && (
        <label className="field">
          <span>ตั้งรหัสผ่าน</span>
          <input value={pass} onChange={(e) => setPass(e.target.value)} placeholder="อย่างน้อย 8 ตัวอักษร" type="password" autoComplete="new-password" />
        </label>
      )}

      {error && <div className="note err">{error}</div>}
      <div className="member-actions">
        <button
          className="btn primary grow"
          onClick={() => saveProfile()}
          disabled={busy || (forced ? incomplete : !name.trim() || (!!pass && pass.length < 8))}
        >
          {busy ? "กำลังบันทึก…" : forced ? "เสร็จสิ้น" : "บันทึก"}
        </button>
      </div>
      {step !== "profile" && (
        <button className="link-btn small" onClick={() => { setStep("manual"); setError(null); }} disabled={busy}>มีบัตรสมาชิก SB อยู่แล้ว (เปลี่ยนเบอร์)</button>
      )}
    </div>
  );
}
