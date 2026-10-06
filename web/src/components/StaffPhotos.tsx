import { useCallback, useEffect, useRef, useState } from "react";
import { apiDelete, apiGet, apiPost, apiUpload, errorMessage, mediaUrl } from "../lib/api";
import { thDate, thTime } from "../lib/format";
import type { StaffMe, StaffPhoto, StaffPhotoAudit } from "../lib/types";
import Icon from "./Icon";

/** ลูกค้าเห็นได้สูงสุดกี่รูปต่อสาขา — ต้องตรงกับ MAX_PUBLIC_PER_BRANCH ฝั่ง backend */
const MAX_SHARED = 5;

const ACTION_TXT: Record<string, string> = { CREATE: "เพิ่ม", UPDATE: "แทนรูป", DELETE: "ลบ", SHARE: "แชร์ให้ลูกค้า", UNSHARE: "เลิกแชร์" };

/** รูปถ่ายของจริงในสาขา (MATNR 20 ตัวโชว์) — เห็นเฉพาะรูปของสาขาตัวเอง
 *
 * ปุ่มแก้/ลบโชว์ตาม can_edit/can_delete ที่ backend คิดมาให้ · หลังบ้านตรวจซ้ำทุกครั้งอยู่ดี
 * สาขาไม่ได้ส่งจากหน้านี้ — backend ใช้สาขาของบัญชีที่ล็อกอินเสมอ
 */
export default function StaffPhotos({ matnr }: { matnr: string }) {
  const [me, setMe] = useState<StaffMe | null>(null);
  const [rows, setRows] = useState<StaffPhoto[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [view, setView] = useState<StaffPhoto | null>(null);
  const [audit, setAudit] = useState<StaffPhotoAudit[] | null>(null);
  const addRef = useRef<HTMLInputElement | null>(null);
  const camRef = useRef<HTMLInputElement | null>(null);
  const replaceRef = useRef<HTMLInputElement | null>(null);
  const replaceId = useRef<string | null>(null);

  const load = useCallback(() => {
    apiGet<StaffPhoto[]>(`/staff/materials/${matnr}/photos`).then(setRows).catch((e) => setErr(errorMessage(e)));
  }, [matnr]);
  useEffect(() => {
    apiGet<StaffMe>("/staff/me").then(setMe).catch(() => setMe(null));
    load();
  }, [load]);

  const can = (p: string) => !!me?.permissions.includes(p);
  const sharedCount = (rows || []).filter((p) => p.is_public).length;
  const sharedFull = sharedCount >= MAX_SHARED;

  const add = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const form = new FormData();
    Array.from(files).forEach((f) => form.append("files", f));
    setBusy("add");
    setErr(null);
    try {
      await apiUpload<StaffPhoto[]>("POST", `/staff/materials/${matnr}/photos`, form);
      load();
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const replace = async (files: FileList | null) => {
    const id = replaceId.current;
    if (!id || !files?.[0]) return;
    const form = new FormData();
    form.append("file", files[0]);
    setBusy(id);
    setErr(null);
    try {
      const p = await apiUpload<StaffPhoto>("PUT", `/staff/photos/${id}`, form);
      setView((v) => (v && v.id === id ? p : v));
      load();
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(null);
      replaceId.current = null;
    }
  };

  const remove = async (p: StaffPhoto) => {
    if (!confirm("ลบรูปนี้? (ระบบเก็บประวัติไว้ ผู้จัดการตรวจย้อนหลังได้)")) return;
    setBusy(p.id);
    setErr(null);
    try {
      await apiDelete(`/staff/photos/${p.id}`);
      setView(null);
      load();
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const share = async (p: StaffPhoto) => {
    setBusy(p.id);
    setErr(null);
    try {
      const n = await apiPost<StaffPhoto>(`/staff/photos/${p.id}/share`, { public: !p.is_public });
      setView((v) => (v && v.id === p.id ? n : v));
      load();
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const showAudit = async () => {
    try {
      setAudit(await apiGet<StaffPhotoAudit[]>(`/staff/photos/audit?matnr=${matnr}`));
    } catch (e) {
      setErr(errorMessage(e));
    }
  };

  const pickReplace = (p: StaffPhoto) => {
    replaceId.current = p.id;
    replaceRef.current?.click();
  };

  return (
    <section className="staff-photos">
      <div className="sp-head">
        <div>
          <b>รูปของจริงในสาขา</b>
          <span className="small muted"> · {me?.branch_name || me?.branch_code || "ยังไม่ผูกสาขา"} · อัปโหลดแล้วเห็นเฉพาะพนักงาน ต้องกดแชร์ลูกค้าถึงจะเห็น · แชร์แล้ว <b>{sharedCount}/{MAX_SHARED}</b> รูป</span>
        </div>
        <div className="row" style={{ gap: 6 }}>
          {can("PRODUCT_IMAGE_AUDIT_VIEW") && <button className="btn sm" onClick={showAudit}><Icon name="history" size={16} /> ประวัติ</button>}
          {can("PRODUCT_IMAGE_CREATE") && me?.branch_code && (
            <>
              {/* capture = เปิดกล้องหลังบนมือถือตรงๆ · บนคอมจะกลายเป็นเลือกไฟล์ธรรมดา */}
              <button className="btn sm" disabled={busy === "add"} onClick={() => camRef.current?.click()}><Icon name="photo_camera" size={16} /> ถ่ายรูป</button>
              <button className="btn sm" disabled={busy === "add"} onClick={() => addRef.current?.click()}><Icon name="add_photo_alternate" size={16} /> {busy === "add" ? "กำลังอัปโหลด…" : "เลือกรูป"}</button>
            </>
          )}
        </div>
      </div>
      <input ref={camRef} type="file" accept="image/*" capture="environment" hidden onChange={(e) => { void add(e.target.files); e.target.value = ""; }} />
      <input ref={addRef} type="file" accept="image/*" multiple hidden onChange={(e) => { void add(e.target.files); e.target.value = ""; }} />
      <input ref={replaceRef} type="file" accept="image/*" hidden onChange={(e) => { void replace(e.target.files); e.target.value = ""; }} />
      {err && <div className="note err small">{err}</div>}
      {me && !me.branch_code && <div className="note warn small">บัญชีนี้ยังไม่ได้ผูกสาขา — ให้แอดมินตั้งสาขาก่อนถึงจะเพิ่มรูปได้</div>}
      {rows === null ? (
        <div className="small muted">กำลังโหลด…</div>
      ) : rows.length === 0 ? (
        <div className="small muted">ยังไม่มีรูปของสาขานี้ — ถ่ายสภาพจริงของตัวโชว์ไว้ให้ลูกค้าดูรอย/สีจริงได้</div>
      ) : (
        <div className="sp-grid">
          {rows.map((p) => (
            <figure key={p.id} className={"sp-item" + (p.mine ? " mine" : "")}>
              {/* ปุ่มไม่วางทับรูป — การ์ดกว้างไม่ถึง 100px วางทับแล้วบังรูปและล้นขอบ */}
              <button className="sp-thumb" onClick={() => setView(p)} aria-label="ดูรูปใหญ่">
                <img src={mediaUrl(p.url)} alt="" loading="lazy" />
                <span className={"sp-state" + (p.is_public ? " on" : "")}>{p.is_public ? "ลูกค้าเห็น" : "เฉพาะพนักงาน"}</span>
              </button>
              <figcaption>
                <span className="tiny">{p.mine ? "รูปของฉัน" : p.owner_employee_name}</span>
                <span className="tiny muted">{thDate(p.updated_at || p.created_at)}</span>
              </figcaption>
              {(p.can_edit || p.can_delete) && (
                <div className="sp-acts">
                  {p.can_edit && (
                    <button className={"sp-share" + (p.is_public ? " on" : "")} disabled={busy === p.id || (!p.is_public && sharedFull)}
                            title={!p.is_public && sharedFull ? `แชร์ครบ ${MAX_SHARED} รูปแล้ว — เลิกแชร์รูปอื่นก่อน` : ""} onClick={() => share(p)}>
                      <Icon name={p.is_public ? "visibility_off" : "share"} size={14} /> {p.is_public ? "เลิกแชร์" : "แชร์"}
                    </button>
                  )}
                  {p.can_edit && <button className="icon-btn sm" disabled={busy === p.id} title="แทนรูป" onClick={() => pickReplace(p)}><Icon name="cached" size={16} /></button>}
                  {p.can_delete && <button className="icon-btn sm" disabled={busy === p.id} title="ลบ" onClick={() => remove(p)}><Icon name="delete" size={16} /></button>}
                </div>
              )}
            </figure>
          ))}
        </div>
      )}

      {view && (
        <div className="modal-backdrop" onClick={() => setView(null)}>
          <div className="modal wide" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h2>{view.matnr} · {view.owner_employee_code} {view.owner_employee_name}</h2>
              <button className="icon-btn" onClick={() => setView(null)} aria-label="ปิด"><Icon name="close" /></button>
            </div>
            <img src={mediaUrl(view.url)} alt="" className="sp-full" />
            <div className="row" style={{ gap: 8, marginTop: 10 }}>
              <span className="small muted">ถ่ายเมื่อ {thDate(view.created_at)} {thTime(view.created_at)}{view.updated_at ? ` · แทนรูปล่าสุด ${thDate(view.updated_at)}` : ""}</span>
              <span style={{ marginLeft: "auto" }} />
              {view.can_edit && (
                <button className={"btn sm" + (view.is_public ? "" : " primary")} disabled={busy === view.id || (!view.is_public && sharedFull)} onClick={() => share(view)}>
                  <Icon name={view.is_public ? "visibility_off" : "share"} size={16} /> {view.is_public ? "เลิกแชร์" : "แชร์ให้ลูกค้าเห็น"}
                </button>
              )}
              {view.can_edit && <button className="btn sm" onClick={() => pickReplace(view)}><Icon name="cached" size={16} /> แทนรูป</button>}
              {view.can_delete && <button className="btn sm" style={{ color: "var(--red)" }} onClick={() => remove(view)}><Icon name="delete" size={16} /> ลบ</button>}
            </div>
          </div>
        </div>
      )}

      {audit && (
        <div className="modal-backdrop" onClick={() => setAudit(null)}>
          <div className="modal wide" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h2>ประวัติรูป · {matnr}</h2>
              <button className="icon-btn" onClick={() => setAudit(null)} aria-label="ปิด"><Icon name="close" /></button>
            </div>
            {audit.length === 0 ? <div className="small muted">ยังไม่มีประวัติ</div> : (
              <div className="sp-audit">
                <table>
                  <thead><tr><th>เมื่อ</th><th>สาขา</th><th>ทำอะไร</th><th>เจ้าของรูป</th><th>คนทำ</th><th>เดิม</th><th>ใหม่</th></tr></thead>
                  <tbody>
                    {audit.map((a, i) => (
                      <tr key={i}>
                        <td className="tiny">{thDate(a.action_at)} {thTime(a.action_at)}</td>
                        <td>{a.branch_code}</td>
                        <td>{ACTION_TXT[a.action] || a.action}</td>
                        <td>{a.image_owner_employee}</td>
                        <td>{a.action_by_employee} <span className="tiny muted">({a.action_by_role})</span></td>
                        <td>{a.old_image_url && <img src={mediaUrl(a.old_image_url)} alt="" />}</td>
                        <td>{a.new_image_url && <img src={mediaUrl(a.new_image_url)} alt="" />}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
