import { useEffect, useState } from "react";
import Icon from "../components/Icon";
import { apiGet, errorMessage } from "../lib/api";

/** สรุปพฤติกรรมผู้ใช้ช่วงทดสอบ — คนเข้ากี่คน ดูอะไร กดอะไร ใส่ตะกร้าอะไร ค้นหาคำว่าอะไร
 *
 *  **ไม่มีลิงก์จากเมนูไหนเลยโดยตั้งใจ** — ช่วงทดสอบให้เฉพาะคนที่รู้ URL เข้ามาดู
 *  แต่ URL ลับไม่ใช่การป้องกัน · ด่านจริงคือ /manager/* ที่เปิดให้เฉพาะ manager กับ admin
 *  (ดู routes.ts) และฝั่ง API ก็กันด้วย require_role อีกชั้น ใครยิงตรงก็ไม่ผ่าน
 *
 *  ตัวเลขทั้งหมดมาจากตาราง user_events ซึ่งเก็บทั้งคนที่ล็อกอินและคนที่ยังไม่ล็อกอิน
 *  (คนไม่ล็อกอินนับด้วยคุกกี้ sb_anon อายุ 90 วัน — ล้างคุกกี้/เปลี่ยนเครื่องจะนับเป็นคนใหม่)
 */
type Row = { key: string; count: number; name?: string | null };
type Overview = {
  days: number;
  visitors: number; members: number; guests: number;
  page_views: number; product_views: number; product_clicks: number;
  searches: number; add_to_cart: number; purchases: number;
  top_pages: Row[]; top_viewed: Row[]; top_clicked: Row[]; top_added: Row[];
  top_searches: { q: string; count: number; clicks: number }[];
  zero_result_searches: { q: string; count: number }[];
};

const RANGES = [1, 7, 30, 90];
const n = (v: number) => v.toLocaleString("en-US");

export default function InsightsPage() {
  const [days, setDays] = useState(7);
  const [data, setData] = useState<Overview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = (d: number) => {
    setBusy(true);
    setErr(null);
    apiGet<Overview>(`/admin/analytics/overview?days=${d}`)
      .then(setData)
      .catch((e) => setErr(errorMessage(e)))
      .finally(() => setBusy(false));
  };
  useEffect(() => { load(days); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [days]);

  /** ตารางอันดับ — สัดส่วนแท่งเทียบกับอันดับหนึ่ง ทำให้เห็นช่องว่างโดยไม่ต้องอ่านตัวเลข */
  const Top = ({ title, hint, rows, label }: { title: string; hint: string; rows: Row[]; label?: (r: Row) => string }) => {
    const max = Math.max(1, ...rows.map((r) => r.count));
    return (
      <div className="ins-card">
        <h3>{title}</h3>
        <p className="tiny muted">{hint}</p>
        {rows.length === 0 ? (
          <p className="tiny muted">ยังไม่มีข้อมูลในช่วงนี้</p>
        ) : (
          <ol className="ins-rank">
            {rows.map((r, i) => (
              <li key={r.key + i}>
                <span className="ins-no">{i + 1}</span>
                <span className="ins-label" title={label ? label(r) : r.key}>{label ? label(r) : r.key}</span>
                <span className="ins-bar"><i style={{ width: `${(r.count / max) * 100}%` }} /></span>
                <b>{n(r.count)}</b>
              </li>
            ))}
          </ol>
        )}
      </div>
    );
  };

  const prod = (r: Row) => (r.name ? `${r.name} · ${r.key}` : r.key);

  return (
    <main className="container ins-page">
      <div className="row between wrap" style={{ alignItems: "center", gap: 12 }}>
        <div>
          <h1 style={{ margin: 0 }}>สรุปการใช้งาน</h1>
          <p className="tiny muted" style={{ margin: "4px 0 0" }}>
            นับรวมคนที่ยังไม่ล็อกอินด้วย · หน้านี้ไม่มีลิงก์จากเมนู ใช้ดูผลช่วงทดสอบ
          </p>
        </div>
        <div className="row" style={{ gap: 6 }}>
          {RANGES.map((d) => (
            <button key={d} className={"btn sm" + (d === days ? " dark" : "")} onClick={() => setDays(d)}>
              {d === 1 ? "วันนี้" : `${d} วัน`}
            </button>
          ))}
          <button className="btn sm" disabled={busy} onClick={() => load(days)} title="ดึงใหม่">
            <Icon name="refresh" size={16} />
          </button>
        </div>
      </div>

      {err && <div className="note err" style={{ marginTop: 12 }}>{err}</div>}
      {!data && !err && <p className="muted" style={{ marginTop: 16 }}>กำลังโหลด…</p>}

      {data && (
        <>
          <div className="ins-kpis">
            {[
              ["คนเข้าเว็บ", data.visitors, "นับคนไม่ซ้ำ ไม่ใช่จำนวนครั้ง"],
              ["สมาชิก", data.members, "ล็อกอินแล้ว"],
              ["ยังไม่ล็อกอิน", data.guests, "นับด้วยคุกกี้"],
              ["เปิดหน้า", data.page_views, "รวมทุกหน้า"],
              ["เปิดดูสินค้า", data.product_views, "เข้าหน้ารายละเอียด"],
              ["กดการ์ดสินค้า", data.product_clicks, "จากหน้าค้นหา/หน้าแรก"],
              ["ค้นหา", data.searches, ""],
              ["ใส่ตะกร้า", data.add_to_cart, ""],
              ["สั่งซื้อ", data.purchases, ""],
            ].map(([t, v, h]) => (
              <div key={t as string} className="ins-kpi">
                <span className="tiny muted">{t as string}</span>
                <b>{n(v as number)}</b>
                {h ? <span className="tiny muted">{h as string}</span> : null}
              </div>
            ))}
          </div>

          <div className="ins-grid">
            <Top title="สินค้าที่เปิดดูมากสุด" hint="เข้าหน้ารายละเอียดสินค้ากี่ครั้ง" rows={data.top_viewed} label={prod} />
            <Top title="สินค้าที่ใส่ตะกร้ามากสุด" hint="สนใจถึงขั้นหยิบใส่ตะกร้า" rows={data.top_added} label={prod} />
            <Top title="สินค้าที่ถูกกดมากสุด" hint="กดจากการ์ดในหน้าค้นหา/หน้าแรก" rows={data.top_clicked} label={prod} />
            <Top title="หน้าที่คนเข้ามากสุด" hint="เส้นทางที่คนเดินบ่อย" rows={data.top_pages} />

            <div className="ins-card">
              <h3>คำค้นยอดนิยม</h3>
              <p className="tiny muted">ค้นแล้วมีคนกดผลลัพธ์กี่ครั้ง — ค้นเยอะแต่กดน้อย แปลว่าผลลัพธ์ยังไม่ตรงใจ</p>
              {data.top_searches.length === 0 ? <p className="tiny muted">ยังไม่มีข้อมูล</p> : (
                <table className="ins-table">
                  <thead><tr><th>คำค้น</th><th>ค้น</th><th>กดผล</th></tr></thead>
                  <tbody>
                    {data.top_searches.map((s) => (
                      <tr key={s.q}>
                        <td>{s.q}</td><td>{n(s.count)}</td>
                        <td className={s.clicks === 0 ? "red" : ""}>{n(s.clicks)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="ins-card">
              <h3>ค้นแล้วไม่เจออะไรเลย</h3>
              <p className="tiny muted">ของที่ลูกค้าหาแต่เราไม่มี หรือระบบค้นหายังจับคำนี้ไม่ได้</p>
              {data.zero_result_searches.length === 0 ? <p className="tiny muted">ไม่มี — ดีแล้ว</p> : (
                <ol className="ins-rank">
                  {data.zero_result_searches.map((s, i) => (
                    <li key={s.q}>
                      <span className="ins-no">{i + 1}</span>
                      <span className="ins-label">{s.q}</span>
                      <b>{n(s.count)}</b>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        </>
      )}
    </main>
  );
}
