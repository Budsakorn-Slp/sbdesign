import { useEffect, useState } from "react";
import { API_BASE, errorMessage } from "../lib/api";
import { downloadBlob, quotationImages, quotationPdf } from "../lib/quotationPdf";
import Icon from "./Icon";

type Kind = "pdf" | "jpg";

/** แชร์/ดาวน์โหลดใบเสนอราคา — PDF หรือรูปภาพ (+ Excel/Word สำหรับพนักงาน)
 *
 * สองขั้น: กดเปิด → สร้างไฟล์ → กด "ส่งไฟล์" อีกที
 * เพราะหน้าต่างแชร์ของมือถือ/iPad ต้องเปิดจากการแตะโดยตรง ถ้าสร้างไฟล์ไปก่อน
 * แล้วค่อยเรียกแชร์ในจังหวะเดียวกัน เครื่องจะปฏิเสธเพราะเลยจังหวะแตะไปแล้ว
 *
 * รูปภาพ: ส่งเข้า LINE แล้วลูกค้าเห็นใบในแชตทันที ไม่ต้องกดเปิดไฟล์ · ใบยาวได้หน้าละรูป
 * ปุ่ม LINE/Facebook/WhatsApp/อีเมล ส่งเป็น "ลิงก์" (แอปพวกนี้รับไฟล์ผ่านลิงก์แชร์ไม่ได้)
 */
export default function QuotationShare({ no, token, staff = false, onClose }: { no: string; token: string | null | undefined; staff?: boolean; onClose: () => void }) {
  const [kind, setKind] = useState<Kind>("pdf");
  const [withImages, setWithImages] = useState(true);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setBusy(true);
    setFiles([]);
    setErr(null);
    const job = kind === "pdf"
      ? quotationPdf(no, token, withImages).then((b) => [new File([b], `${no}${withImages ? "" : "-no-images"}.pdf`, { type: "application/pdf" })])
      : quotationImages(no, token, withImages);
    job
      .then((f) => live && setFiles(f))
      .catch((e) => live && setErr(errorMessage(e)))
      .finally(() => live && setBusy(false));
    return () => {
      live = false;
    };
  }, [no, token, withImages, kind]);

  const label = kind === "pdf" ? "PDF" : "รูปภาพ";
  const canShareFile = files.length > 0 && typeof navigator.canShare === "function" && navigator.canShare({ files });
  const link = token ? `${location.origin}/q/${no}?t=${token}` : `${location.origin}/q/${no}`;
  const text = `ใบเสนอราคา ${no} จาก SB Design Square`;
  const enc = encodeURIComponent;
  const exportUrl = (format: "xlsx" | "docx") => `${API_BASE}/quotations/${no}/export?format=${format}${token ? `&t=${token}` : ""}`;
  const size = files.reduce((n, f) => n + f.size, 0);

  const shareFile = async () => {
    if (!files.length) return;
    try {
      await navigator.share({ files, title: text, text });
      setMsg("ส่งแล้ว");
    } catch (e) {
      if ((e as Error).name !== "AbortError") setErr(errorMessage(e));
    }
  };

  const download = () => {
    // หลายรูป: เว้นจังหวะนิดหน่อย บางเบราว์เซอร์บล็อกการดาวน์โหลดหลายไฟล์ที่ยิงพร้อมกัน
    files.forEach((f, i) => setTimeout(() => downloadBlob(f, f.name), i * 400));
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>แชร์ใบเสนอราคา {no}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="ปิด"><Icon name="close" /></button>
        </div>
        <div className="qs-kind" role="tablist">
          <button role="tab" aria-selected={kind === "pdf"} className={kind === "pdf" ? "on" : ""} disabled={busy} onClick={() => setKind("pdf")}>
            <Icon name="picture_as_pdf" size={16} /> PDF
          </button>
          <button role="tab" aria-selected={kind === "jpg"} className={kind === "jpg" ? "on" : ""} disabled={busy} onClick={() => setKind("jpg")}>
            <Icon name="image" size={16} /> รูปภาพ (JPG)
          </button>
        </div>
        <label className="row small" style={{ gap: 6, margin: "10px 0" }}>
          <input type="checkbox" checked={withImages} onChange={(e) => setWithImages(e.target.checked)} disabled={busy} /> ใส่รูปสินค้าในไฟล์
        </label>

        {busy && <div className="note small">กำลังสร้าง{label}…</div>}
        {err && <div className="note err small">{err}</div>}
        {files.length > 0 && (
          <div className="qs-file">
            <Icon name={kind === "pdf" ? "picture_as_pdf" : "image"} size={28} />
            <span className="grow">
              <b>{files.length === 1 ? files[0].name : `${files.length} รูป (${files[0].name} …)`}</b>
              <small>{Math.max(1, Math.round(size / 1024))} KB</small>
            </span>
          </div>
        )}

        <div className="qs-main">
          {canShareFile && (
            <button className="btn primary block" onClick={shareFile}><Icon name="ios_share" size={18} /> ส่ง{label} (LINE · Messenger · อื่นๆ)</button>
          )}
          <button className="btn block" disabled={!files.length} onClick={download}>
            <Icon name="download" size={18} /> ดาวน์โหลด{label}
          </button>
        </div>

        {/* ไฟล์ที่แก้ต่อได้ — เครื่องมือพนักงาน ลูกค้าใช้ PDF/รูปพอ */}
        {staff && (
          <div className="qs-links" style={{ marginTop: 12 }}>
            <a className="qs-chip" href={exportUrl("xlsx")}><Icon name="table_view" size={16} /> Excel (.xlsx)</a>
            <a className="qs-chip" href={exportUrl("docx")}><Icon name="description" size={16} /> Word (.docx)</a>
          </div>
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
