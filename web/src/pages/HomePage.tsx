import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import FeedStrip from "../components/FeedStrip";
import Icon from "../components/Icon";
import Placeholder from "../components/Placeholder";
import ProductCard from "../components/ProductCard";
import ProductRow from "../components/ProductRow";
import { useContent } from "../lib/content";
import type { HomeContent, MaterialCard, MediaTile } from "../lib/types";

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

/** ปุ่มเลื่อนของแถว 2 ชั้น — วางไว้ใต้แถว ชิดขวา แทนที่จะอยู่บนหัวข้อ */
function ScrollFoot({ onPrev, onNext }: { onPrev: () => void; onNext: () => void }) {
  return (
    <div className="sec-foot">
      <button className="arrow" onClick={onPrev} aria-label="ก่อนหน้า"><Icon name="chevron_left" size={20} /></button>
      <button className="arrow dark" onClick={onNext} aria-label="ถัดไป"><Icon name="chevron_right" size={20} /></button>
    </div>
  );
}

function Strip({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={"strip " + (className || "")}>{children}</div>;
}

/** แถวเลื่อนซ้ายขวา · ใส่ autoMs เพื่อให้เลื่อนไปหน้าถัดไปเอง (หยุดตอนเมาส์ชี้อยู่บนแถว) */
function useScroller(autoMs?: number) {
  const ref = useRef<HTMLDivElement>(null);
  const paused = useRef(false);

  const step = (dir: number) => {
    const el = ref.current;
    const max = el ? el.scrollWidth - el.clientWidth : 0;
    if (!el || max <= 0) return;
    const d = Math.round(el.clientWidth * 0.8);
    // สุดทางแล้ววนกลับอีกฝั่ง จะได้เลื่อนเองไปเรื่อยๆ ไม่ค้างอยู่ท้ายแถว
    const to =
      dir > 0
        ? el.scrollLeft >= max - 2 ? 0 : Math.min(el.scrollLeft + d, max)
        : el.scrollLeft <= 2 ? max : Math.max(el.scrollLeft - d, 0);
    el.scrollTo({ left: to, behavior: "smooth" });
  };

  useEffect(() => {
    if (!autoMs) return;
    const id = setInterval(() => !paused.current && step(1), autoMs);
    return () => clearInterval(id);
  }, [autoMs]);

  const hover = {
    onMouseEnter: () => { paused.current = true; },
    onMouseLeave: () => { paused.current = false; },
  };
  return { ref, prev: () => step(-1), next: () => step(1), hover };
}

function ProductStrip({ title, items, more }: { title: string; items: MaterialCard[]; more: string }) {
  return (
    <section className="container sec">
      <ProductRow title={title} items={items} more={more} />
    </section>
  );
}

/** แบนเนอร์ใหญ่ — เปลี่ยนเองทุก autoMs (หยุดตอนเมาส์ชี้อยู่บนแบนเนอร์) */
function useSlideshow(count: number, autoMs: number) {
  const [i, setI] = useState(0);
  const paused = useRef(false);

  useEffect(() => {
    if (count < 2) return;
    const id = setInterval(() => !paused.current && setI((x) => (x + 1) % count), autoMs);
    return () => clearInterval(id);
  }, [count, autoMs]);

  return {
    index: count ? i % count : 0,
    go: (n: number) => setI((x) => (x + n + count) % count),
    set: setI,
    hover: {
      onMouseEnter: () => { paused.current = true; },
      onMouseLeave: () => { paused.current = false; },
    },
  };
}

export default function HomePage() {
  const { content } = useContent();
  const hero = useSlideshow(content?.hero_slides.length ?? 0, 3000);
  const catSc = useScroller(6000);
  const brandSc = useScroller(5000);

  if (!content) {
    return (
      <main className="container sec">
        <div className="ph" style={{ height: 420, borderRadius: 10 }}>กำลังโหลดหน้าแรก…</div>
      </main>
    );
  }

  const slides = content.hero_slides;
  const slide = hero.index;
  const s = slides[slide];
  const inspirations = content.inspirations ?? [];
  const topCategories = content.top_categories ?? [];
  const brandTiles = content.brand_tiles ?? [];
  const inspireTabs = content.inspire_tabs ?? [];

  return (
    <main className="home">
      {/* HERO — แบนเนอร์แคมเปญหลักซ้าย + HOME INSPIRATIONS 4 ช่องขวา ตัวหนังสืออยู่ในภาพแล้ว ไม่ซ้อนทับอีก */}
      <section className="container hero-row">
        <div className={"hero" + (s.image ? " hero-img" : "")} {...hero.hover}>
          {s.image ? (
            /* ซ้อนทุกใบไว้แล้วสลับความทึบ ภาพถัดไปจึงโหลดไว้ก่อน ไม่วูบตอนเปลี่ยนสไลด์ */
            slides.map((x, i) => (
              <Link key={x.id} to={x.href} className={"hero-pic" + (i === slide ? " on" : "")} aria-hidden={i !== slide}>
                {/* ช่องซ้ายสูงกว่ากว้าง ใช้ไฟล์ -MB ที่สัดส่วนใกล้เคียงกว่า จะได้ไม่โดน crop จนเนื้อหาหาย */}
                <img src={x.image_mb ?? x.image} alt={x.alt ?? ""} />
              </Link>
            ))
          ) : (
            <>
              <div className="hero-art ph">
                <div className="hero-art-lbl mono">{s.art}<br /><span className="tiny">แคมเปญหลัก — เปลี่ยนได้ {slides.length} สไลด์</span></div>
              </div>
              <div className="hero-copy">
                <span className="chip">{s.tag}</span>
                <h2>{s.title}</h2>
              </div>
              <div className="hero-foot">
                <span className="hero-note">{s.note}</span>
                <span className="dots">
                  {slides.map((x, i) => (
                    <button key={x.id} className={"dot" + (i === slide ? " on" : "")} onClick={() => hero.set(i)} aria-label={`สไลด์ ${i + 1}`} />
                  ))}
                </span>
                <Link to={s.href} className="btn dark">{s.cta} <Icon name="arrow_forward" size={18} /></Link>
              </div>
            </>
          )}
          {slides.length > 1 && (
            <>
              <button className="hero-arrow left" onClick={() => hero.go(-1)} aria-label="ก่อนหน้า"><Icon name="chevron_left" /></button>
              <button className="hero-arrow right" onClick={() => hero.go(1)} aria-label="ถัดไป"><Icon name="chevron_right" /></button>
              <span className="hero-dots">
                {slides.map((x, i) => (
                  <button key={x.id} className={"hero-dot" + (i === slide ? " on" : "")} onClick={() => hero.set(i)} aria-label={`สไลด์ ${i + 1}`} />
                ))}
              </span>
            </>
          )}
        </div>

        <div className="hero-tiles">
          {inspirations.length
            ? inspirations.slice(0, 4).map((it) => (
                <Link key={it.id} to={it.href} className="insp" title={it.label ?? undefined}>
                  <img src={it.image} alt={it.alt ?? it.label ?? ""} />
                </Link>
              ))
            : content.promo_cards.map((p) => (
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

      {/* FIND YOUR INSPIRATION — บล็อกแท็บ ดึงมาจาก CMS หน้าแรกของ sbdesignsquare.com ต่อจากแบนเนอร์ */}
      {inspireTabs.length > 0 && <InspireBlock tabs={inspireTabs} />}

      {/* TOP CATEGORIES — 2 แถว เลื่อนซ้ายขวา */}
      <section className="container sec sec-lead">
        <SectionHead title="หมวดหมู่สินค้า" />
        <div className={"cat-tiles" + (topCategories.length ? " cat-scroll" : "")} ref={catSc.ref} {...catSc.hover}>
          {topCategories.length
            ? topCategories.map((c) => (
                <Link key={c.id} to={c.href} className="cat-tile">
                  <img className="cat-img" src={c.image} alt="" loading="lazy" />
                  <span className="cat-lbl">{c.label}</span>
                </Link>
              ))
            : content.category_tiles.map((c) => (
                <Link key={c.category} to={`/search?category=${c.category}`} className="cat-tile">
                  <span className="ph cat-ico mono">88<br />×88</span>
                  <span className="cat-lbl">{c.label}</span>
                </Link>
              ))}
        </div>
        <ScrollFoot onPrev={catSc.prev} onNext={catSc.next} />
      </section>

      <FeedStrip title="สินค้าขายดีจริงจากยอดสั่งซื้อ" path="/best-sellers?limit=8" more="/search?tag=bestseller" />
      <ProductStrip title="สินค้าขายดี" items={content.bestsellers} more="/search?tag=bestseller" />

      {/* ROOM ROWS */}
      <section className="container sec">
        <SectionHead title="ช้อปตามหมวดสินค้า" />
        <div className="room-rows">
          {content.room_rows.map((r) => (
            <RoomRow key={r.room} label={r.label} href={r.href || `/search?room=${r.room}`} items={r.items} />
          ))}
        </div>
      </section>

      {/* BRANDS — โลโก้จริงจากหน้า EXCLUSIVE BRANDS ของ Magento (เกือบร้อยแบรนด์ เลยทำเป็น 2 แถวเลื่อน) */}
      <section className="container sec sec-lead">
        <SectionHead title="EXCLUSIVE BRAND" />
        <div className={"brand-tiles" + (brandTiles.length ? " brand-scroll" : "")} ref={brandSc.ref} {...brandSc.hover}>
          {brandTiles.length
            ? brandTiles.map((b) => (
                <Link key={b.id} to={b.href} className="brand-tile" title={b.label ?? undefined}>
                  <img src={b.image} alt={b.label ?? ""} loading="lazy" />
                </Link>
              ))
            : content.brands.map((b) => (
                <Link key={b.id} to={`/search?q=${encodeURIComponent(b.name.split(" ")[0])}`} className="brand-tile">
                  <Placeholder ratio="3 / 1" label={<>LOGO 3:1<br />{b.name}</>} />
                </Link>
              ))}
        </div>
        {brandTiles.length > 0 && <ScrollFoot onPrev={brandSc.prev} onNext={brandSc.next} />}
      </section>

      <ProductStrip title="สินค้าใหม่" items={content.new_products} more="/search?tag=new" />
      <FeedStrip title="ดูล่าสุด" path="/me/recently-viewed?limit=8" more="/account/recent" />
    </main>
  );
}

/** บล็อก FIND YOUR INSPIRATION — แท็บละหลายใบ 3 ใบบน + 2 ใบกว้างล่าง เหมือนหน้าเว็บจริง */
function InspireBlock({ tabs }: { tabs: NonNullable<HomeContent["inspire_tabs"]> }) {
  const [i, setI] = useState(0);
  const tab = tabs[Math.min(i, tabs.length - 1)];
  return (
    <section className="container sec sec-lead">
      <SectionHead title="FIND YOUR INSPIRATION" />
      <div className="insp-tabs" role="tablist">
        {tabs.map((t, n) => (
          <button key={t.key} role="tab" aria-selected={n === i} className={"insp-tab" + (n === i ? " on" : "")} onClick={() => setI(n)}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="insp-grid">
        {tab.items.slice(0, 5).map((it, n) => (
          <InspTile key={it.id} tile={it} wide={n >= 3} />
        ))}
      </div>
    </section>
  );
}

/** ปลายทางของการ์ดเป็นบทความบนเว็บจริง (ขึ้นต้น http) ฝั่งเราไม่มีหน้าคู่กัน เลยเปิดแท็บใหม่ */
function InspTile({ tile, wide }: { tile: MediaTile; wide: boolean }) {
  const inner = (
    <>
      <img src={tile.image} alt={tile.alt ?? tile.label ?? ""} loading="lazy" />
      {tile.label && <span className="insp-cap">{tile.label}</span>}
    </>
  );
  const cls = "insp-cell" + (wide ? " wide" : "");
  return tile.href.startsWith("http") ? (
    <a className={cls} href={tile.href} target="_blank" rel="noreferrer">{inner}</a>
  ) : (
    <Link className={cls} to={tile.href}>{inner}</Link>
  );
}

function RoomRow({ label, href, items }: { label: string; href: string; items: MaterialCard[] }) {
  const sc = useScroller();
  return (
    <div className="room-row">
      <Link to={href} className="room-row-lbl">{label}</Link>
      <button className="arrow" onClick={sc.prev} aria-label="ก่อนหน้า"><Icon name="chevron_left" size={18} /></button>
      <div className="room-row-strip" ref={sc.ref}>
        {/* การ์ดสินค้าจริงของกลุ่มนั้น ทรงเดียวกับแถวสินค้าอื่นบนหน้าแรก */}
        {items.map((it) => (
          <ProductCard key={it.matnr} item={it} compact />
        ))}
      </div>
      <button className="arrow" onClick={sc.next} aria-label="ถัดไป"><Icon name="chevron_right" size={18} /></button>
    </div>
  );
}
