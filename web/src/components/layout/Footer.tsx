import { Link } from "react-router-dom";
import { useContent } from "../../lib/content";
import Icon from "../Icon";

const SOCIAL = ["thumb_up", "chat", "photo_camera", "work", "smart_display", "music_note"];

export default function Footer() {
  const { content } = useContent();
  if (!content) return <footer className="ftr" />;
  return (
    <footer className="ftr">
      <div className="container">
        <div className="ftr-top">
          <div className="ftr-promos">
            {content.footer_promos.map((p) => (
              <div key={p.head} className="ftr-promo">
                <h3>{p.head}</h3>
                <p>{p.body}</p>
                <Link to={p.href} className="btn dark sm">{p.cta}</Link>
              </div>
            ))}
          </div>
          {content.footer_cols.map((c) => (
            <div key={c.head} className="ftr-col">
              <h4>{c.head}</h4>
              <ul>
                {c.items.map((it) => (
                  <li key={it}><a href="#">{it}</a></li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="ftr-mid">
          <div className="row wrap" style={{ gap: 10 }}>
            {SOCIAL.map((s) => (
              <span key={s} className="ftr-social"><Icon name={s} size={18} /></span>
            ))}
            <span className="ftr-sep" />
            {content.payments.map((p) => (
              <span key={p} className="ftr-pay mono">{p}</span>
            ))}
          </div>
          <div className="row" style={{ gap: 10 }}>
            <span className="pill"><Icon name="settings" size={16} /> การตั้งค่าคุกกี้</span>
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
              <li key={l}><a href="#">{l}</a></li>
            ))}
          </ul>
        </div>
      </div>
    </footer>
  );
}
