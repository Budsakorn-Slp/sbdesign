import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiGet } from "../lib/api";

type InfoPageOut = { slug: string; title: string; body_html: string; source_url: string | null };

/** หน้าเนื้อหาคงที่ — วิธีสั่งซื้อ / การรับประกัน / นโยบาย ฯลฯ
 *
 * เนื้อหายกมาจาก CMS ของเว็บจริง (ดู backend/app/etl/sync_cms_pages.py) เพราะเป็นข้อความ
 * เชิงนโยบายที่ต้องตรงกับที่บริษัทประกาศไว้จริง ส่วนหน้าตาเป็นของเราล้วนๆ —
 * ETL ถอด style/class/script ของต้นทางทิ้งหมดแล้ว เหลือแต่แท็กเนื้อหาให้ CSS เราจัดเอง
 */
export default function InfoPage() {
  const { slug = "" } = useParams();
  const [page, setPage] = useState<InfoPageOut | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let alive = true;
    setPage(null);
    setMissing(false);
    apiGet<InfoPageOut>(`/pages/${encodeURIComponent(slug)}`)
      .then((d) => alive && setPage(d))
      .catch(() => alive && setMissing(true));
    // เลื่อนกลับขึ้นบนสุดเมื่อเปลี่ยนหน้า — หน้าพวกนี้ยาว ถ้าค้างกลางหน้าเดิมจะงงว่ากดแล้วไม่ไปไหน
    window.scrollTo(0, 0);
    return () => {
      alive = false;
    };
  }, [slug]);

  if (missing) {
    return (
      <main className="container sec info-page">
        <h1>ไม่พบหน้านี้</h1>
        <p className="muted">หน้าที่คุณเปิดอาจถูกย้ายหรือเปลี่ยนชื่อไปแล้ว</p>
        <Link to="/" className="btn dark">กลับหน้าแรก</Link>
      </main>
    );
  }

  if (!page) return <main className="container sec info-page"><div className="ph" style={{ height: 320 }}>กำลังโหลด…</div></main>;

  return (
    <main className="container sec info-page">
      <nav className="crumbs small muted">
        <Link to="/">หน้าแรก</Link> › <span>{page.title}</span>
      </nav>
      <h1>{page.title}</h1>
      {/* เนื้อหาถูกล้าง script/style ทิ้งตั้งแต่ตอน sync แล้ว (ดู etl/html_clean.py)
          จึงใส่เป็น HTML ตรงๆ ได้ — ไม่ได้รับ HTML จากผู้ใช้หรือจากอินเทอร์เน็ตสดๆ */}
      <div className="info-body" dangerouslySetInnerHTML={{ __html: page.body_html }} />
    </main>
  );
}
