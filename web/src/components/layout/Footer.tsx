import { Link } from "react-router-dom";
import { useContent } from "../../lib/content";
import { useLang } from "../../lib/i18n";
import { SOCIAL_ICONS, type SocialKey } from "../../lib/socialIcons";
import Icon from "../Icon";

/** ช่องทางโซเชียลของ SB Design Square — ไอคอนเป็นโลโก้แบรนด์จริง ไม่ใช่ไอคอนทั่วไป
 *  คนสแกนหาไอคอนที่คุ้นตา ไอคอนกลางๆ อย่าง "รูปกล้อง" แทน Instagram ทำให้หาไม่เจอ */
const SOCIAL: { key: SocialKey; href: string }[] = [
  { key: "facebook", href: "https://www.facebook.com/sbdesignsquare" },
  { key: "line", href: "https://line.me/R/ti/p/@sbdesignsquare" },
  { key: "instagram", href: "https://www.instagram.com/sbdesignsquare" },
  { key: "tiktok", href: "https://www.tiktok.com/@sbdesignsquare" },
  { key: "youtube", href: "https://www.youtube.com/@sbdesignsquare" },
];

/** โลโก้แบรนด์วาดเป็น SVG ชิ้นเดียว — ใช้ currentColor ตามสีของกล่องที่ครอบอยู่ */
function SocialIcon({ name, size = 17 }: { name: SocialKey; size?: number }) {
  const ic = SOCIAL_ICONS[name];
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" role="img" aria-hidden="true">
      <path d={ic.path} />
    </svg>
  );
}

/** ลิงก์ใน footer — ปลายทางในแอปใช้ Link (ไม่โหลดหน้าใหม่) ส่วนลิงก์ออกเว็บอื่นใช้ <a>
 *  บางปลายทาง (บริการหลังการขาย) ยังเป็นระบบแยกของบริษัท ไม่มีหน้าคู่กันในแอปเรา */
function FooterLink({ label, href, className }: { label: string; href: string; className?: string }) {
  const external = /^https?:\/\//.test(href);
  return external ? (
    <a href={href} className={className} target="_blank" rel="noopener noreferrer">{label}</a>
  ) : (
    <Link to={href} className={className}>{label}</Link>
  );
}

export default function Footer() {
  const { content } = useContent();
  const { t } = useLang();
  if (!content) return <footer className="ftr" />;
  return (
    <footer className="ftr">
      <div className="container">
        <div className="ftr-top">
          <div className="ftr-promos">
            {content.footer_promos.map((p) => (
              <div key={p.head} className="ftr-promo">
                <h3>{t(p.head)}</h3>
                <p>{p.body}</p>
                <FooterLink label={p.cta} href={p.href} className="btn dark sm" />
              </div>
            ))}
          </div>
          {content.footer_cols.map((c) => (
            <div key={c.head} className="ftr-col">
              <h4>{t(c.head)}</h4>
              <ul>
                {c.items.map((it) => (
                  <li key={it.href}><FooterLink {...it} /></li>
                ))}
              </ul>
            </div>
          ))}
          {/* ย้ายขึ้นมาอยู่แถวบน — เดิมอยู่แถวล่างคู่กับตราชำระเงิน ทั้งที่ตรงนี้ว่างอยู่สองช่อง
              (กริดตั้งไว้ 5 คอลัมน์ แต่มีเนื้อหาแค่ 3) */}
          <div className="ftr-col ftr-follow">
            <h4>{t("ติดตามเรา")}</h4>
            <div className="row wrap" style={{ gap: 8 }}>
              {SOCIAL.map((s) => (
                <a key={s.key} className="ftr-social" href={s.href} target="_blank" rel="noopener noreferrer"
                   title={SOCIAL_ICONS[s.key].label} aria-label={SOCIAL_ICONS[s.key].label}>
                  <SocialIcon name={s.key} />
                </a>
              ))}
            </div>
          </div>
        </div>

        <div className="ftr-mid">
          <div className="row wrap" style={{ gap: 10 }}>
            {content.payments.map((p) => (
              <span key={p} className="ftr-pay mono">{p}</span>
            ))}
          </div>
          <div className="row" style={{ gap: 10 }}>
            <span className="pill"><Icon name="settings" size={16} /> {t("การตั้งค่าคุกกี้")}</span>
            <span className="pill"><Icon name="language" size={16} /> <b>TH</b> ไทย</span>
          </div>
        </div>

        <div className="ftr-bottom">
          <div className="muted small">
            <div>{content.support_line}</div>
            <div>© SB Design Square 2026 · บริษัท เอส.บี.อุตสาหกรรมเครื่องเรือน จำกัด</div>
          </div>
          <ul className="ftr-legal">
            {content.legal_links.map((l) => (
              <li key={l.href}><FooterLink {...l} /></li>
            ))}
          </ul>
        </div>
      </div>
    </footer>
  );
}
