import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Icon from "../components/Icon";
import { apiGet, apiPut, apiUpload, errorMessage, mediaUrl } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { QuotationTemplate } from "../lib/types";

type Form = Pick<QuotationTemplate, "display_name" | "phone" | "bank_accounts" | "footer_terms" | "standard_remark">;
const FIELDS: (keyof Form)[] = ["display_name", "phone", "bank_accounts", "footer_terms", "standard_remark"];

/** template ใบเสนอราคาส่วนตัวของ DS — ใส่ครั้งเดียว ทุกใบที่ออกใหม่ดึงไปใช้เอง
 *
 * ช่องไหนเว้นว่าง ใบจะใช้ค่ากลางของบริษัท · แก้ทีหลังไม่ไปเปลี่ยนใบที่ออกไปแล้ว
 */
export default function QuotationTemplatePage() {
  const auth = useAuth();
  const [tpl, setTpl] = useState<QuotationTemplate | null>(null);
  const [form, setForm] = useState<Form>({ display_name: "", phone: "", bank_accounts: "", footer_terms: "", standard_remark: "" });
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const logoRef = useRef<HTMLInputElement | null>(null);

  const take = (t: QuotationTemplate) => {
    setTpl(t);
    setForm(Object.fromEntries(FIELDS.map((k) => [k, t[k] || ""])) as Form);
  };
  useEffect(() => {
    apiGet<QuotationTemplate>("/staff/quotation-template").then(take).catch((e) => setMsg({ ok: false, text: errorMessage(e) }));
  }, []);

  if (!auth.user || !["sales", "manager", "admin"].includes(auth.role || "")) {
    return <main className="container sec"><div className="note">เฉพาะพนักงาน — <Link to="/staff">เข้าสู่ระบบพนักงาน</Link></div></main>;
  }

  const save = async () => {
    setBusy("save");
    setMsg(null);
    try {
      take(await apiPut<QuotationTemplate>("/staff/quotation-template", form));
      setMsg({ ok: true, text: "บันทึกแล้ว — ใบเสนอราคาที่ออกต่อจากนี้จะใช้ข้อมูลชุดนี้" });
    } catch (e) {
      setMsg({ ok: false, text: errorMessage(e) });
    } finally {
      setBusy(null);
    }
  };

  const upload = async (files: FileList | null) => {
    if (!files?.[0]) return;
    const fd = new FormData();
    fd.append("file", files[0]);
    setBusy("logo");
    setMsg(null);
    try {
      take(await apiUpload<QuotationTemplate>("POST", "/staff/quotation-template/logo", fd));
    } catch (e) {
      setMsg({ ok: false, text: errorMessage(e) });
    } finally {
      setBusy(null);
    }
  };

  const changed = tpl !== null && FIELDS.some((k) => (form[k] || "") !== (tpl[k] || ""));
  const field = (k: keyof Form) => ({ value: form[k] || "", onChange: (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value })) });

  return (
    <main className="container sec tpl-page">
      <Link to="/sales" className="row small muted" style={{ marginBottom: 10 }}><Icon name="arrow_back" size={18} /> ตะกร้าที่กำลังดูแล</Link>
      <h1 style={{ marginTop: 0 }}>Template ใบเสนอราคาของฉัน</h1>
      {tpl && (
        <p className="small muted">
          {tpl.employee_code} – {tpl.employee_name} · สาขา {tpl.branch_code || "-"} {tpl.branch_name || ""}
          <br />รหัสพนักงานกับสาขามาจากบัญชีที่ล็อกอิน แก้จากหน้านี้ไม่ได้
        </p>
      )}
      <div className="card tpl-card">
        <div className="tpl-logo">
          {tpl?.logo_url ? <img src={mediaUrl(tpl.logo_url)} alt="โลโก้" /> : <div className="tpl-logo-empty small muted">ยังไม่มีโลโก้</div>}
          <button className="btn sm" disabled={busy === "logo"} onClick={() => logoRef.current?.click()}>
            <Icon name="image" size={16} /> {busy === "logo" ? "กำลังอัปโหลด…" : tpl?.logo_url ? "เปลี่ยนโลโก้" : "อัปโหลดโลโก้"}
          </button>
          <input ref={logoRef} type="file" accept="image/*" hidden onChange={(e) => { void upload(e.target.files); e.target.value = ""; }} />
        </div>
        <label className="tpl-f"><span>ชื่อที่พิมพ์บนใบ</span><input {...field("display_name")} maxLength={120} placeholder={tpl?.employee_name || ""} /></label>
        <label className="tpl-f"><span>เบอร์ติดต่อ</span><input {...field("phone")} maxLength={32} placeholder="08x-xxx-xxxx" /></label>
        <label className="tpl-f"><span>บัญชีธนาคารสำหรับโอน</span><textarea {...field("bank_accounts")} rows={3} placeholder={"ธ.กสิกรไทย 142-1-06853-0 บจ. เอสบี ดีไซน์สแควร์\n(บรรทัดละบัญชี)"} /></label>
        <label className="tpl-f"><span>หมายเหตุมาตรฐาน</span><textarea {...field("standard_remark")} rows={2} placeholder="ต่อท้ายหมายเหตุของทุกใบ เช่น ราคารวม VAT แล้ว" /></label>
        <label className="tpl-f">
          <span>เงื่อนไขท้ายบิล <small className="muted">(บรรทัดละข้อ · เว้นว่าง = ใช้เงื่อนไขกลางของบริษัท)</small></span>
          <textarea {...field("footer_terms")} rows={6} placeholder={"ใบเสนอราคานี้มีกำหนดอายุถึงวันที่ {month_end}\nลูกค้าเป็นผู้จัดเตรียมพื้นที่ให้พร้อมในการติดตั้ง"} />
        </label>
        <p className="tiny muted" style={{ margin: 0 }}>
          พิมพ์ <code>{"{month_end}"}</code> ตรงที่ต้องการวันที่ — ระบบใส่ <b>วันสุดท้ายของเดือนที่ออกใบ</b> ให้เอง
          {tpl && <> (ถ้าออกใบวันนี้ = <b>{tpl.month_end_preview}</b>)</>}
        </p>
        <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
          <button className="btn primary" disabled={!changed || busy === "save"} onClick={save}>{busy === "save" ? "กำลังบันทึก…" : "บันทึก"}</button>
        </div>
        {msg && <div className={"note small " + (msg.ok ? "ok" : "err")}>{msg.text}</div>}
      </div>
    </main>
  );
}
