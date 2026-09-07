import { useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import FeedStrip from "../components/FeedStrip";
import Icon from "../components/Icon";
import Placeholder from "../components/Placeholder";
import ProductCard from "../components/ProductCard";
import { useContent } from "../lib/content";
import type { MaterialCard } from "../lib/types";

function SectionHead({ title, more, onPrev, onNext }: { title: string; more?: string; onPrev?: () => void; onNext?: () => void }) {
  return (
    <div className="sec-head">
      <h2>{title}</h2>
      <div className="row">
        {more && <Link to={more} className="sec-more">ดูทั้งหมด ›</Link>}
        {onPrev && onNext && (
          <div className="arrows">
            <button className="arrow" onClick={onPrev} aria-label="ก่อนหน้า"><Icon name="chevron_left" size={20} /></button>
            <button className="arrow dark" onClick={onNext} aria-label="ถัดไป"><Icon name="chevron_right" size={20} /></button>
          </div>
        )}
      </div>
    </div>
  );
}

function Strip({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={"strip " + (className || "")}>{children}</div>;
}

function useScroller() {
  const ref = useRef<HTMLDivElement>(null);
  const by = (dir: number) => () => {
    const el = ref.current;
    if (el) el.scrollBy({ left: dir * Math.round(el.clientWidth * 0.8), behavior: "smooth" });
  };
  return { ref, prev: by(-1), next: by(1) };
}

function ProductStrip({ title, items, more }: { title: string; items: MaterialCard[]; more: string }) {
  if (!items.length) return null;
  return (
    <section className="container sec">
      <SectionHead title={title} more={more} />
      <div className="pgrid">
        {items.slice(0, 4).map((it) => (
          <ProductCard key={it.matnr} item={it} />
        ))}
      </div>
    </section>
  );
}

export default function HomePage() {
  const { content } = useContent();
  const [slide, setSlide] = useState(0);
  const newSc = useScroller();
  const catSc = useScroller();

  if (!content) {
    return (
      <main className="container sec">
        <div className="ph" style={{ height: 420, borderRadius: 10 }}>กำลังโหลดหน้าแรก…</div>
      </main>
    );
  }

  const slides = content.hero_slides;
  const s = slides[slide % slides.length];

  return (
    <main className="home">
      {/* HERO + PROMO CARDS */}
      <section className="container hero-row">
        <div className="hero">
          <div className="hero-art ph">
            <div className="hero-art-lbl mono">{s.art}<br /><span className="tiny">แคมเปญหลัก — เปลี่ยนได้ {slides.length} สไลด์</span></div>
          </div>
          <div className="hero-copy">
            <span className="chip">{s.tag}</span>
            <h2>{s.title}</h2>
          </div>
          <button className="hero-arrow left" onClick={() => setSlide((slide - 1 + slides.length) % slides.length)} aria-label="ก่อนหน้า"><Icon name="chevron_left" /></button>
          <button className="hero-arrow right" onClick={() => setSlide((slide + 1) % slides.length)} aria-label="ถัดไป"><Icon name="chevron_right" /></button>
          <div className="hero-foot">
            <span className="hero-note">{s.note}</span>
            <span className="dots">
              {slides.map((x, i) => (
                <button key={x.id} className={"dot" + (i === slide ? " on" : "")} onClick={() => setSlide(i)} aria-label={`สไลด์ ${i + 1}`} />
              ))}
            </span>
            <Link to={s.href} className="btn dark">{s.cta} <Icon name="arrow_forward" size={18} /></Link>
          </div>
        </div>
        <div className="promo-grid">
          {content.promo_cards.map((p) => (
            <div key={p.tag} className="promo">
              <span className="chip">{p.tag}</span>
              <h3>{p.title}</h3>
              <div className="ph promo-art mono">logo strip · fluid</div>
              <div className="promo-foot">
                <span className="muted small">{p.note}</span>
                <Link to={p.href} className="btn sm">ช้อปเลย <Icon name="arrow_forward" size={16} /></Link>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* SERVICES */}
      <section className="container services">
        {content.services.map((sv) => (
          <div key={sv.label} className="service">
            <span className="service-ico"><Icon name={sv.icon} size={26} /></span>
            <span>{sv.label}</span>
          </div>
        ))}
      </section>

      {/* CATEGORY TILES 4x2 */}
      <section className="container sec">
        <SectionHead title="หมวดหมู่สินค้า" onPrev={catSc.prev} onNext={catSc.next} />
        <div className="cat-tiles" ref={catSc.ref}>
          {content.category_tiles.map((c) => (
            <Link key={c.category} to={`/search?category=${c.category}`} className="cat-tile">
              <span className="ph cat-ico mono">88<br />×88</span>
              <span className="cat-lbl">{c.label}</span>
            </Link>
          ))}
        </div>
      </section>

      {/* NEW FROM SB */}
      <section className="container sec">
        <SectionHead title="ช้อปสินค้าใหม่จาก SB" onPrev={newSc.prev} onNext={newSc.next} />
        <Strip className="new-strip">
          <div className="strip-in" ref={newSc.ref}>
            {content.new_collections.map((n) => (
              <Link key={n.label} to={n.href} className="new-card">
                <Placeholder ratio="3 / 4" label={<>3:4 · art<br />738 × 984</>} />
                <span className="new-lbl">{n.label}</span>
              </Link>
            ))}
          </div>
        </Strip>
      </section>

      <ProductStrip title="ดีลพิเศษวันนี้" items={content.deals} more="/search?tag=deal" />
      <FeedStrip title="สินค้าขายดีจริงจากยอดสั่งซื้อ" path="/best-sellers?limit=8" more="/search?tag=bestseller" />
      <ProductStrip title="สินค้าขายดี" items={content.bestsellers} more="/search?tag=bestseller" />

      {/* ROOM ROWS */}
      <section className="container sec">
        <SectionHead title="ช้อปตามหมวดสินค้าเพื่อบ้าน" />
        <div className="room-rows">
          {content.room_rows.map((r) => (
            <RoomRow key={r.room} label={r.label} room={r.room} items={r.items} />
          ))}
        </div>
      </section>

      {/* SHOP BY ROOM */}
      <section className="container sec">
        <SectionHead title="ช้อปตามห้อง" more="/search" />
        <div className="room-tiles">
          {content.rooms.map((r) => (
            <Link key={r.room} to={`/search?room=${r.room}`} className="room-tile">
              <Placeholder ratio="8 / 5" label={<>ROOM SCENE · 8:5</>} />
              <span className="room-lbl">{r.label}</span>
            </Link>
          ))}
        </div>
      </section>

      {/* BRANDS */}
      <section className="container sec">
        <SectionHead title="ช้อปตามแบรนด์" />
        <div className="brand-tiles">
          {content.brands.map((b) => (
            <Link key={b.id} to={`/search?q=${encodeURIComponent(b.name.split(" ")[0])}`} className="brand-tile">
              <Placeholder ratio="3 / 1" label={<>LOGO 3:1<br />{b.name}</>} />
            </Link>
          ))}
          <a href="#" className="brand-tile more mono">SEE MORE BRAND</a>
        </div>
      </section>

      <ProductStrip title="สินค้าใหม่" items={content.new_products} more="/search?tag=new" />
      <FeedStrip title="ดูล่าสุด" path="/me/recently-viewed?limit=8" more="/account/recent" />
    </main>
  );
}

function RoomRow({ label, room, items }: { label: string; room: string; items: { label: string; category: string }[] }) {
  const sc = useScroller();
  return (
    <div className="room-row">
      <Link to={`/search?room=${room}`} className="room-row-lbl">{label}</Link>
      <button className="arrow" onClick={sc.prev} aria-label="ก่อนหน้า"><Icon name="chevron_left" size={18} /></button>
      <div className="room-row-strip" ref={sc.ref}>
        {items.map((it) => (
          <Link key={it.category} to={`/search?category=${it.category}`} className="room-item">
            <Placeholder ratio="1 / 1" label={<>150 × 150</>} />
            <span>{it.label}</span>
          </Link>
        ))}
      </div>
      <button className="arrow" onClick={sc.next} aria-label="ถัดไป"><Icon name="chevron_right" size={18} /></button>
    </div>
  );
}
