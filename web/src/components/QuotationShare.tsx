import { useEffect, useState } from "react";
import { API_BASE, errorMessage } from "../lib/api";
import { openGoogleSheet } from "../lib/gsheet";
import { downloadBlob, quotationPdf } from "../lib/quotationPdf";
import Icon from "./Icon";

/** แชร์/ดาวน์โหลดใบเสนอราคาเป็นไฟล์ PDF
 *
 * สองขั้น: กดเปิด → สร้างไฟล์ → กด "ส่งไฟล์" อีกที
 * เพราะหน้าต่างแชร์ของมือถือ (โดยเฉพาะ iPhone) ต้องเปิดจากการแตะโดยตรง ถ้าสร้างไฟล์ไปก่อน
 * แล้วค่อยเรียกแชร์ในจังหวะเดียวกัน เครื่องจะปฏิเสธเพราะเลยจังหวะแตะไปแล้ว
 *
 * ปุ่ม LINE/Facebook/WhatsApp/อีเมล ส่งเป็น "ลิงก์" (แอปพวกนี้รับไฟล์ผ่านลิงก์แชร์ไม่ได้)
 * ส่งเป็น "ไฟล์" ใช้ปุ่มแรก ซึ่งเปิดหน้าต่างแชร์ของเครื่องที่มี LINE/Messenger ให้เลือกอยู่แล้ว
 */
export default function QuotationShare({ no, token, staff = false, onClose }: { no: string; token: string | null | undefined; staff?: boolean; onClose: () => void }) {
  const [withImages, setWithImages] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setBusy(true);
    setFile(null);
    setErr(null);
    quotationPdf(no, token, withImages)
      .then((b) => live && setFile(new File([b], `${no}${withImages ? "" : "-no-images"}.pdf`, { type: "application/pdf" })))
      .catch((e) => live && setErr(errorMessage(e)))
      .finally(() => live && setBusy(false));
    return () => {
      live = false;
    };
  }, [no, token, withImages]);

  const canShareFile = !!file && typeof navigator.canShare === "function" && navigator.canShare({ files: [file] });
  const link = token ? `${location.origin}/q/${no}?t=${token}` : `${location.origin}/q/${no}`;
  const text = `ใบเสนอราคา ${no} จาก SB Design Square`;
  const enc = encodeURIComponent;
  const exportUrl = (format: "xlsx" | "csv") => `${API_BASE}/quotations/${no}/export?format=${format}${token ? `&t=${token}` : ""}`;

  const shareFile = async () => {
    if (!file) return;
    try {
      await navigator.share({ files: [file], title: text, text });
      setMsg("ส่งแล้ว");
    } catch (e) {
      if ((e as Error).name !== "AbortError") setErr(errorMessage(e));
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>แชร์ใบเสนอราคา {no}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="ปิด"><Icon name="close" /></button>
        </div>
        <label className="row small" style={{ gap: 6, marginBottom: 10 }}>
          <input type="checkbox" checked={withImages} onChange={(e) => setWithImages(e.target.checked)} disabled={busy} /> ใส่รูปสินค้าในไฟล์
        </label>

        {busy && <div className="note small">กำลังสร้างไฟล์ PDF…</div>}
        {err && <div className="note err small">{err}</div>}
        {file && (
          <div className="qs-file">
            <Icon name="picture_as_pdf" size={28} />
            <span className="grow"><b>{file.name}</b><small>{Math.max(1, Math.round(file.size / 1024))} KB</small></span>
          </div>
        )}

        <div className="qs-main">
          {canShareFile && (
            <button className="btn primary block" onClick={shareFile}><Icon name="ios_share" size={18} /> ส่งไฟล์ PDF (LINE · Messenger · อื่นๆ)</button>
          )}
          <button className="btn block" disabled={!file} onClick={() => file && downloadBlob(file, file.name)}>
            <Icon name="download" size={18} /> ดาวน์โหลด PDF
          </button>
        </div>
        {!canShareFile && file && (
          <p className="tiny muted" style={{ margin: "6px 0 0" }}>เครื่องนี้ส่งไฟล์เข้าแอปโดยตรงไม่ได้ — ดาวน์โหลดแล้วแนบเอง หรือส่งเป็นลิงก์ด้านล่าง</p>
        )}

        {/* ไฟล์ตาราง — เครื่องมือพนักงาน (แก้ตัวเลข/แนบระบบอื่นต่อ) ลูกค้าใช้ PDF พอ */}
        {staff && (
          <>
            <div className="qs-label small muted">ไฟล์ตาราง (แก้ไขต่อได้)</div>
            <div className="qs-links">
              <a className="qs-chip" href={exportUrl("xlsx")}><Icon name="table_view" size={16} /> Excel (.xlsx)</a>
              <a className="qs-chip" href={exportUrl("csv")}><Icon name="download" size={16} /> CSV</a>
              <button className="qs-chip" onClick={() => openGoogleSheet(no, token).then(setMsg).catch((e) => setErr(errorMessage(e)))}><Icon name="grid_on" size={16} /> Google Sheets</button>
            </div>
          </>
        )}

        <div className="qs-label small muted">หรือส่งเป็นลิงก์เปิดดูใบ</div>
        <div className="qs-links">
          <a className="qs-chip line" href={`https://line.me/R/share?text=${enc(`${text}\n${link}`)}`} target="_blank" rel="noreferrer">LINE</a>
          <a className="qs-chip fb" href={`https://www.facebook.com/sharer/sharer.php?u=${enc(link)}`} target="_blank" rel="noreferrer">Facebook</a>
          <a className="qs-chip wa" href={`https://wa.me/?text=${enc(`${text}\n${link}`)}`} target="_blank" rel="noreferrer">WhatsApp</a>
          <a className="qs-chip" href={`mailto:?subject=${enc(text)}&body=${enc(`${text}\n${link}`)}`}>อีเมล</a>
          <button className="qs-chip" onClick={() => { navigator.clipboard?.writeText(link); setMsg("คัดลอกลิงก์แล้ว"); }}>คัดลอกลิงก์</button>
        </div>
        {msg && <div className="note ok small" style={{ marginTop: 8, wordBreak: "break-all" }}>{msg}</div>}
      </div>
    </div>
  );
}
