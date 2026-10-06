import { useEffect, useState } from "react";
import { apiGet, mediaUrl } from "../lib/api";
import type { BranchPhotos as Group } from "../lib/types";
import Icon from "./Icon";

/** รูปของจริงของตัวโชว์ แยกตามสาขา — ลูกค้าเห็นเฉพาะรูปที่พนักงานกดแชร์แล้ว
 *
 * ตัวโชว์แต่ละสาขาคนละชิ้น สภาพ/รอย/สีจริงไม่เหมือนกัน ลูกค้าเลือกสาขาแล้วดูของชิ้นนั้นได้เลย
 * ไม่มีรูปที่แชร์ = ไม่แสดงส่วนนี้ (ไม่ต้องโชว์กล่องว่าง)
 */
export default function BranchPhotos({ matnr }: { matnr: string }) {
  const [groups, setGroups] = useState<Group[]>([]);
  const [pick, setPick] = useState<string | null>(null);
  const [big, setBig] = useState<string | null>(null);

  useEffect(() => {
    setPick(null);
    apiGet<Group[]>(`/materials/${matnr}/branch-photos`)
      .then((g) => { setGroups(g); setPick(g[0]?.branch_code ?? null); })
      .catch(() => setGroups([]));
  }, [matnr]);

  if (groups.length === 0) return null;
  const cur = groups.find((g) => g.branch_code === pick) || groups[0];

  return (
    <section className="branch-photos">
      <b className="small"><Icon name="photo_library" size={16} /> รูปของจริงที่สาขา</b>
      <p className="tiny muted" style={{ margin: "2px 0 8px" }}>ตัวโชว์แต่ละสาขาเป็นคนละชิ้น สภาพจริงอาจต่างกัน — เลือกสาขาเพื่อดูชิ้นที่วางอยู่ที่นั่น</p>
      <div className="bp-tabs" role="tablist">
        {groups.map((g) => (
          <button key={g.branch_code} role="tab" aria-selected={g.branch_code === cur.branch_code}
                  className={"bp-tab" + (g.branch_code === cur.branch_code ? " on" : "")} onClick={() => setPick(g.branch_code)}>
            {g.branch_name} <small>({g.photos.length})</small>
          </button>
        ))}
      </div>
      <div className="bp-grid">
        {cur.photos.map((p) => (
          <button key={p.id} className="bp-thumb" onClick={() => setBig(p.url)} aria-label="ดูรูปใหญ่">
            <img src={mediaUrl(p.url)} alt={`รูปจริงที่ ${cur.branch_name}`} loading="lazy" />
          </button>
        ))}
      </div>
      {big && (
        <div className="modal-backdrop" onClick={() => setBig(null)}>
          <div className="modal wide" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h2>{cur.branch_name}</h2>
              <button className="icon-btn" onClick={() => setBig(null)} aria-label="ปิด"><Icon name="close" /></button>
            </div>
            <img src={mediaUrl(big)} alt="" className="sp-full" />
          </div>
        </div>
      )}
    </section>
  );
}
