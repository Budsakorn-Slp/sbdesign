import { useEffect, useState } from "react";
import Icon from "./Icon";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import { getDistricts, getProvinces } from "../lib/geo";
import type { District, Province } from "../lib/types";

/** ตรวจสอบคิวจัดส่ง — เลือกชุดรถ + ปลายทาง แล้วสรุปค่าจัดส่งทั้งก้อนก่อนจองคิว
 *
 *  อยู่ในบล็อกคิวจัดส่ง ไม่ใช่ในแถบ "ค่าขนส่ง (เปิด Mat)" เพราะตอบคนละคำถาม:
 *    Mat A534/A761  = คิดจากยอดบิลอย่างเดียว ไม่สนว่าส่งไปไหน
 *    ตรงนี้         = คิดจากปลายทาง ซึ่งเป็นเรื่องเดียวกับการจัดคิวรถ
 *
 *  ค่าเพิ่มมีสองชั้นและบวกกันได้ แยกบรรทัดให้พนักงานอธิบายลูกค้าได้ว่าเงินก้อนไหนมาจากอะไร
 *    fleet        กรุงเทพฟรี · ต่างจังหวัดมีค่าเดินทาง
 *    พื้นที่ห่างไกล เกาะ/ทางเขา/พื้นที่พิเศษ คิดเพิ่มอีกต่อ
 *
 *  ระบบไม่บวกให้เอง — พนักงานกดบวกเอง บางเคสลูกค้าไปรับเองที่ท่าเรือ/จุดนัด
 */
type Fleet = { code: string; name: string; bkk_fee: number; upcountry_fee: number };
type Extra = {
  area: string; area_label: string;
  fleet: string | null; fleet_fee: string;
  remote: boolean; remote_scope: string | null; remote_note: string | null; remote_fee: string;
  extra_total: string;
  /** true = ระบบบวกให้เองไม่ได้ (เกาะ/ชายแดนใต้ หรือไม่พบอัตราของอำเภอนี้) ต้องให้ทีมขนส่งประเมิน */
  needs_review: boolean;
};

const baht = (v: string | number) => Number(v).toLocaleString("th-TH");

export default function RemoteAreaCheck({ cartId, rev, onAdded, onReady, onPostcode, onBlocked }: {
  cartId: string; rev?: string | number; onAdded?: () => void;
  /** บอกหน้าแม่ว่าคำนวณค่าจัดส่งเรียบร้อยแล้วหรือยัง — ปฏิทินจองคิวเปิดได้ก็ต่อเมื่อพร้อม */
  onReady?: (ready: boolean) => void;
  /** รหัสไปรษณีย์ตัวแทนของจังหวัดที่เลือก — หน้าแม่เอาไปขอเขตส่ง/คิวรถต่อ
   *  (เลิกให้พนักงานพิมพ์ที่อยู่กับรหัส ปณ. เองแล้ว เลือกจังหวัดอย่างเดียวพอ) */
  onPostcode?: (pc: string) => void;
  /** ขาดอะไรถึงยังจองคิวไม่ได้ — null = พร้อมแล้ว */
  onBlocked?: (why: string | null) => void;
}) {
  const [fleets, setFleets] = useState<Fleet[]>([]);
  const [fleet, setFleet] = useState("");
  const [provs, setProvs] = useState<Province[]>([]);
  const [dists, setDists] = useState<District[]>([]);
  const [pvId, setPvId] = useState(0);
  const [dtId, setDtId] = useState(0);
  const [extra, setExtra] = useState<Extra | null>(null);
  const [mat, setMat] = useState<{ matnr: string; fee: string } | null>(null);
  // บรรทัดค่าส่งเพิ่มเติมที่เปิดไว้แล้วในบิล (Mat A776) — อ่านจากเซิร์ฟเวอร์ ไม่ใช่จำในหน้าจอ
  // ถ้าจำในหน้าจออย่างเดียว พอปิดหน้าต่างแล้วเปิดใหม่จะนึกว่ายังไม่เคยเปิด แล้วล็อกปฏิทินค้าง
  const [extraLine, setExtraLine] = useState<{ fee: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [added, setAdded] = useState(false);

  useEffect(() => {
    getProvinces().then(setProvs).catch(() => setProvs([]));
    apiGet<Fleet[]>("/sales/fleets").then((f) => { setFleets(f); setFleet(f[0]?.code || ""); }).catch(() => setFleets([]));
  }, []);

  // ค่าขนส่งที่เปิด Mat ไว้ — เอามาโชว์ในสรุปเพื่อให้เห็นยอดรวมจริง ไม่ใช่เห็นแต่ส่วนเพิ่ม
  useEffect(() => {
    apiGet<{ matnr: string; fee: string; current: { matnr: string; fee: string } | null; extra: { fee: string } | null }>(
      `/sales/carts/${cartId}/shipping-charge`,
    )
      .then((r) => { setMat(r.current ? { matnr: r.current.matnr, fee: r.current.fee } : null); setExtraLine(r.extra); })
      .catch(() => { setMat(null); setExtraLine(null); });
  }, [cartId, rev]);

  // เลือกจังหวัดแล้วดึงอำเภอให้เอง
  useEffect(() => {
    setDtId(0);
    if (!pvId) { setDists([]); return; }
    getDistricts(pvId).then(setDists).catch(() => setDists([]));
    const pv = provs.find((p) => p.province_id === pvId);
    if (pv?.postcode) onPostcode?.(pv.postcode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pvId, provs]);

  // เปลี่ยนชุดรถ/ปลายทาง = ตัวเลขที่เช็คไว้ใช้ไม่ได้แล้ว ต้องกดเช็คใหม่
  // (เดิมคำนวณให้อัตโนมัติตั้งแต่เลือกจังหวัด ทั้งที่ยังไม่ได้เลือกอำเภอ
  //  ค่าที่ขึ้นมาจึงเป็นของ "ทั้งจังหวัด" ซึ่งมักไม่ใช่ค่าจริงของอำเภอที่จะส่ง)
  useEffect(() => { setExtra(null); setAdded(false); setMsg(null); }, [pvId, dtId, fleet]);

  const canCheck = Boolean(fleet && pvId && dtId);
  const [checking, setChecking] = useState(false);
  const check = async () => {
    const pv = provs.find((p) => p.province_id === pvId);
    const dt = dists.find((d) => d.district_id === dtId);
    if (!pv || !dt) return;
    setChecking(true);
    setMsg(null);
    try {
      const q = new URLSearchParams({ province: pv.name_th, district: dt.name_th, fleet });
      setExtra(await apiGet<Extra>(`/sales/delivery-extra?${q}`));
    } catch (e) {
      setMsg(errorMessage(e));
    } finally {
      setChecking(false);
    }
  };

  /** เปิดค่าส่งเพิ่มเติมเป็น "บรรทัดของตัวเอง" (Mat A776) ไม่เอาไปรวมกับบรรทัดเทียร์
   *  ลูกค้าจะได้เห็นว่าเงินก้อนไหนมาจากอะไร — ยอดรวมไปบวกกันที่กล่องสรุปคำสั่งซื้อ */
  const addToCharge = async () => {
    if (!extra || Number(extra.extra_total) <= 0) return;
    setBusy(true);
    setMsg(null);
    try {
      const why = [
        `${extra.fleet || "fleet"} ${extra.area_label} +${baht(extra.fleet_fee)}`,
        extra.remote ? `พื้นที่ห่างไกล ${extra.remote_scope} +${baht(extra.remote_fee)}` : null,
      ].filter(Boolean).join(" · ");
      await apiPost(`/sales/carts/${cartId}/shipping-charge`, {
        matnr: "A533",
        fee: extra.extra_total,
        remark: why.slice(0, 300),
      });
      setMsg(`เปิด Mat A533 ค่าส่งต่างจังหวัด ${baht(extra.extra_total)} บาท เป็นอีกบรรทัดในบิลแล้ว`);
      setAdded(true);
      onAdded?.();
    } catch (e) {
      setMsg(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const matFee = Number(mat?.fee || 0);
  const extraTotal = Number(extra?.extra_total || 0);

  // เปิดค่าส่งเพิ่มเติมเข้าบิลแล้วหรือยัง — ดูจากบิลจริงเป็นหลัก (added เป็นแค่ผลของการกดรอบนี้
  // ไว้ให้จอตอบสนองทันทีก่อนข้อมูลใหม่จะกลับมา)
  const extraDone = (extraTotal <= 0 && !extra?.needs_review) || added || Number(extraLine?.fee || 0) >= extraTotal;
  const placePicked = Boolean(pvId && dtId);
  // ต้องเปิดค่าขนส่งตามยอดบิล (Mat A534/A761) ก่อน ถึงจะเช็คค่าส่งพิเศษได้
  //
  // เพราะค่าส่งพิเศษเป็น "ส่วนเพิ่ม" ของค่าขนส่งหลัก ไม่ใช่ค่าขนส่งที่ยืนอยู่ได้เอง
  // ถ้าเปิดแต่ส่วนเพิ่มโดยไม่มีตัวหลัก บิลจะมีแต่ค่าพื้นที่ห่างไกลโดยไม่มีค่าขนส่งพื้นฐาน
  const tierOpen = Boolean(mat);
  // พร้อมจองคิว = เลือกชุดรถ + เลือกปลายทาง + ถ้ามีค่าเพิ่มต้องเปิดเข้าบิลแล้ว
  // ไม่งั้นพนักงานจองวันไปก่อนแล้วค่อยรู้ทีหลังว่าค่าส่งเพิ่มอีกสามพัน ต้องโทรแจ้งลูกค้าใหม่
  const ready = tierOpen && Boolean(fleet && extra && placePicked) && extraDone;
  useEffect(() => { onReady?.(ready); }, [ready, onReady]);
  // บอกหน้าแม่ด้วยว่า "ขาดอะไร" ไม่ใช่แค่ "ยังไม่พร้อม" — ข้อความล็อกจะได้ตรงกับความจริง
  useEffect(() => {
    onBlocked?.(!tierOpen ? "เปิดค่าขนส่งตามยอดบิล (Mat) ที่แถบ “ค่าขนส่ง (เปิด Mat)” ก่อน"
      : !fleet ? "เลือกชุดรถก่อน"
      : !placePicked ? "เลือกจังหวัดและอำเภอปลายทางก่อน"
      : !extra ? "กดปุ่มรถท้ายแถวเพื่อเช็คค่าส่งต่างจังหวัดก่อน"
      : extra.needs_review ? "พื้นที่นี้ระบบคิดค่าส่งให้ไม่ได้ — ให้ทีมขนส่งประเมินแล้วใส่ที่แถบค่าขนส่งเอง"
      : !extraDone ? "กดปุ่ม “เปิดค่าส่งเพิ่มเติม” ในขั้นที่ 2 ก่อน"
      : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tierOpen, fleet, placePicked, extra, extraDone]);

  return (
    <div className="qcheck">
      <div className="qcheck-head">
        <span className="promo-step-no on">1</span>
        <b>เลือกชุดรถและปลายทาง</b>
      </div>

      {!tierOpen && (
        <div className="note warn small">
          <Icon name="lock" size={16} /> เปิดค่าขนส่งตามยอดบิลก่อน — กดที่แถบ “ค่าขนส่ง (เปิด Mat)” ด้านบน
          แล้วกด “เปิด Mat เข้าบิล” จากนั้นค่อยกลับมาเช็คค่าส่งพิเศษตรงนี้
        </div>
      )}

      <div className="qcheck-grid">
        <label className="field">
          <span>Fleet (ชุดรถ)</span>
          <select value={fleet} disabled={!tierOpen} onChange={(e) => setFleet(e.target.value)}>
            {fleets.map((f) => <option key={f.code} value={f.code}>{f.name}</option>)}
          </select>
        </label>
        <label className="field">
          <span>จังหวัด *</span>
          <select value={pvId} disabled={!tierOpen} onChange={(e) => setPvId(Number(e.target.value))}>
            <option value={0}>กรุณาเลือก</option>
            {provs.map((p) => <option key={p.province_id} value={p.province_id}>{p.name_th}</option>)}
          </select>
        </label>
        <label className="field">
          <span>อำเภอ / เขต *</span>
          <select value={dtId} onChange={(e) => setDtId(Number(e.target.value))} disabled={!tierOpen || !pvId}>
            <option value={0}>{!tierOpen ? "—" : pvId ? "กรุณาเลือก" : "เลือกจังหวัดก่อน"}</option>
            {dists.map((d) => <option key={d.district_id} value={d.district_id}>{d.name_th}</option>)}
          </select>
        </label>
        {/* ปุ่มเช็คอยู่ท้ายแถวเดียวกับช่องเลือก — มันคือ "กดดูผลของสิ่งที่เพิ่งเลือก"
            วางแยกบรรทัดแล้วสายตาต้องกระโดดลงไปหา ทั้งที่มือยังอยู่ที่ดรอปดาวน์ */}
        {tierOpen && (
          <div className="qcheck-go">
            <button
              className={"icon-btn dark" + (extra ? " done" : "")}
              type="button"
              disabled={!canCheck || checking}
              onClick={check}
              title={extra ? "เช็คแล้ว — กดเพื่อเช็คใหม่" : "เช็คค่าส่งพิเศษ"}
              aria-label={extra ? "เช็คค่าส่งพิเศษอีกครั้ง" : "เช็คค่าส่งพิเศษ"}
            >
              <Icon name={checking ? "hourglass_top" : extra ? "check" : "local_shipping"} size={18} />
            </button>
          </div>
        )}
      </div>

      {/* ปุ่มเช็คเป็นไอคอนเล็กท้ายแถว ไม่ใช่ปุ่มเต็มความกว้าง —
          มันเป็นแค่ "กดดูผล" ของช่องที่เพิ่งเลือก ไม่ใช่ปุ่มยืนยันที่ต้องเด่นกว่าทุกอย่างในหน้าต่าง */}
      {tierOpen && (
        <div className="tiny muted">
          {!canCheck ? "เลือกชุดรถ จังหวัด และอำเภอให้ครบ แล้วกดปุ่มรถท้ายแถว"
            : extra ? "เปลี่ยนปลายทางแล้วกดเช็คใหม่ได้" : "กดปุ่มรถท้ายแถวเพื่อเช็คค่าส่งพิเศษ"}
        </div>
      )}

      {extra && (
        <div className="qcheck-sum">
          <div className="qcheck-head" style={{ margin: "0 0 4px" }}>
            <span className="promo-step-no on">2</span>
            <b>ตรวจค่าจัดส่ง</b>
          </div>
          <div className="qc-row">
            <span>ค่าขนส่ง (Mat {mat?.matnr || "ยังไม่ได้เปิด"})</span>
            <b>{mat ? `${baht(matFee)} บาท` : "—"}</b>
          </div>
          <div className="qc-row">
            <span>ค่าส่งต่างจังหวัด · {extra.remote_scope || extra.area_label}{extra.fleet ? ` · ${extra.fleet}` : ""}</span>
            <b className={extraTotal > 0 ? undefined : "green"}>
              {extraTotal > 0 ? `${baht(extraTotal)} บาท` : extra.needs_review ? "—" : "ไม่มีค่าส่งเพิ่ม"}
            </b>
          </div>
          {extra.needs_review && (
            <div className="qc-row warn">
              <span><Icon name="warning" size={14} /> {extra.remote_note}</span>
              <b>รอทีมขนส่ง</b>
            </div>
          )}
          <div className="qc-row total">
            <span>รวมค่าจัดส่ง</span>
            <b>{baht(matFee + extraTotal)} บาท</b>
          </div>
          {extraTotal > 0 && extraDone && (
            <div className="tiny green">เปิดค่าส่งต่างจังหวัดเข้าบิลแล้ว — เลือกวันจัดส่งได้เลย</div>
          )}
          {extraTotal > 0 && !extraDone && (
            <button className="btn dark sm block" type="button" disabled={busy} onClick={addToCharge}>
              {busy ? "กำลังบันทึก…" : `เปิดค่าส่งต่างจังหวัด ${baht(extraTotal)} บาท เข้าบิล`}
            </button>
          )}
          {msg && <div className="tiny muted">{msg}</div>}
        </div>
      )}
    </div>
  );
}
