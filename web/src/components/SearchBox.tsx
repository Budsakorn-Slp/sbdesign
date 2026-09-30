import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiGet } from "../lib/api";
import { useContent } from "../lib/content";
import { useLang } from "../lib/i18n";
import type { SuggestOut } from "../lib/types";
import { imageSources } from "../lib/images";
import Icon from "./Icon";
import Placeholder from "./Placeholder";

const RECENT_KEY = "sb_recent_searches";
const RECENT_MAX = 6;
const DEBOUNCE_MS = 180; // พิมพ์รัวๆ แล้วยิงทุกตัวอักษรจะหนักฝั่งเซิร์ฟเวอร์เปล่าๆ

function readRecent(): string[] {
  try {
    const raw = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    return Array.isArray(raw) ? raw.filter((x) => typeof x === "string").slice(0, RECENT_MAX) : [];
  } catch {
    return []; // โหมดไม่ระบุตัวตน/ปิดคุกกี้ — ไม่มีประวัติก็แค่ไม่โชว์
  }
}

/** ลบคำค้นเก่าทีละคำ — ปุ่มกากบาทบนชิป */
function forgetSearch(term: string): string[] {
  const next = readRecent().filter((x) => x !== term);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    /* เก็บไม่ได้ก็ไม่เป็นไร */
  }
  return next;
}

/* ช้อปตามงบ — ตัวเลขมาจากของที่ลูกค้าถามบ่อยที่สุด 4 อย่าง ไม่ได้ทำเป็นตัวกรองแบบไดนามิก
   เพราะจุดประสงค์คือ "กดแล้วได้ของเลย" ไม่ใช่ให้ตั้งค่าเอง (ตั้งเองได้ที่หน้าผลลัพธ์อยู่แล้ว) */
const BUDGETS: { label: string; href: string }[] = [
  { label: "โซฟาไม่เกิน 10,000", href: "/search?q=" + encodeURIComponent("โซฟา") + "&max_price=10000" },
  { label: "เตียงไม่เกิน 10,000", href: "/search?q=" + encodeURIComponent("เตียง") + "&max_price=10000" },
  { label: "โต๊ะทำงานไม่เกิน 5,000", href: "/search?q=" + encodeURIComponent("โต๊ะทำงาน") + "&max_price=5000" },
  { label: "เก้าอี้ทำงานไม่เกิน 3,000", href: "/search?q=" + encodeURIComponent("เก้าอี้ทำงาน") + "&max_price=3000" },
];

/** ไอคอนหน้าชื่อหมวด — เดาจากคำในชื่อ ไม่ได้เก็บไว้ในฐาน (ชื่อหมวดมาจากเว็บจริง เปลี่ยนได้) */
function catIcon(label: string): string {
  const has = (...w: string[]) => w.some((x) => label.includes(x));
  if (has("นอน")) return "bed";
  if (has("นั่งเล่น")) return "weekend";
  if (has("โซฟา", "พักผ่อน")) return "chair";
  if (has("อาหาร", "ครัว")) return "restaurant";
  if (has("ทำงาน", "เกม")) return "desktop_windows";
  if (has("ตกแต่ง")) return "format_paint";
  if (has("ตัวโชว์")) return "storefront";
  if (has("พิเศษ")) return "star";
  return "category";
}

export function rememberSearch(q: string) {
  const term = q.trim();
  if (!term) return;
  try {
    const next = [term, ...readRecent().filter((x) => x !== term)].slice(0, RECENT_MAX);
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    /* เก็บไม่ได้ก็ไม่เป็นไร ไม่ใช่ข้อมูลที่ขาดไม่ได้ */
  }
}

/** ช่องค้นหาพร้อมกล่องแนะนำ — พิมพ์ไปขึ้นไป, เลื่อนด้วยลูกศร, Enter เข้าหน้าผลลัพธ์ */
export default function SearchBox({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useLang();
  const { content } = useContent();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<SuggestOut | null>(null);
  const [recent, setRecent] = useState<string[]>([]);
  const [cursor, setCursor] = useState(-1); // -1 = ยังไม่ได้เลือกอะไร Enter จะค้นตามที่พิมพ์
  const [busy, setBusy] = useState(false); // กำลังรอผลจากเซิร์ฟเวอร์ — เอาไว้หมุนวงกลมบอกผู้ใช้
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) {
      setData(null);
      setBusy(false);
      return;
    }
    // ทิ้งผลของคำเก่าเสมอ — พิมพ์เร็วๆ แล้วคำตอบมาสลับลำดับ กล่องจะโชว์ของคำก่อนหน้า
    let alive = true;
    const timer = setTimeout(() => {
      setBusy(true);
      apiGet<SuggestOut>(`/materials/suggest?q=${encodeURIComponent(term)}`)
        .then((d) => alive && setData(d))
        .catch(() => alive && setData(null))
        .finally(() => alive && setBusy(false));
    }, DEBOUNCE_MS);
    return () => {
      // ยกเลิกคำเก่า: alive=false กันไม่ให้ setBusy(false) ของคำก่อนหน้าไปดับวงหมุนของคำใหม่
      alive = false;
      clearTimeout(timer);
    };
  }, [q]);

  // รายการทั้งหมดในกล่อง เรียงตามที่ตาเห็น เพื่อให้ลูกศรขึ้น/ลงเดินได้ตรงลำดับ
  const rows: { label: string; go: () => void }[] = q.trim().length < 2
    ? recent.map((t) => ({ label: t, go: () => submit(t) }))
    : [
        ...(data?.suggestions || []).map((s) => ({ label: s.label, go: () => go(s.href, s.label) })),
        ...(data?.items || []).map((m) => ({ label: m.name_th, go: () => go(`/p/${m.matnr}`, q) })),
      ];

  const close = useCallback(() => {
    setOpen(false);
    setCursor(-1);
    onNavigate?.();
  }, [onNavigate]);

  const go = (href: string, remember: string) => {
    rememberSearch(remember);
    close();
    nav(href);
  };

  const submit = (term: string) => {
    const t = term.trim();
    rememberSearch(t);
    close();
    nav(t ? `/search?q=${encodeURIComponent(t)}` : "/search");
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (cursor >= 0 && rows[cursor]) rows[cursor].go();
    else submit(q);
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") return close();
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    if (!rows.length) return;
    setOpen(true);
    setCursor((c) => (e.key === "ArrowDown" ? (c + 1) % rows.length : (c <= 0 ? rows.length : c) - 1));
  };

  const focus = () => {
    setRecent(readRecent());
    setOpen(true);
  };

  const products = data?.items || [];
  const tips = data?.suggestions || [];
  const showRecent = q.trim().length < 2 && recent.length > 0;
  // ยังไม่ได้พิมพ์ = กล่อง "แนะนำ" (หมวด/ค้นล่าสุด/งบ + ขายดี) · พิมพ์แล้ว = กล่องผลแนะนำแบบเดิม
  const discover = q.trim().length < 2;
  // เอาจาก content ที่หัวเว็บโหลดไว้แล้ว เปิดกล่องจึงขึ้นทันที ไม่ต้องรอยิง API ใหม่
  const cats = (content?.main_nav || []).filter((m) => m.href);
  const best = (content?.bestsellers || []).slice(0, 6);
  const showPanel = open && (discover ? cats.length > 0 || best.length > 0 : tips.length > 0 || products.length > 0);

  return (
    <div className="hdr-search-wrap" ref={box}>
      <form className="hdr-search" onSubmit={onSubmit} role="search" autoComplete="off">
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setCursor(-1);
            setOpen(true);
          }}
          onFocus={focus}
          onKeyDown={onKey}
          placeholder={t("ค้นหาสินค้า แบรนด์ หรือรหัสสินค้า")}
          aria-label="ค้นหา"
          role="combobox"
          aria-expanded={showPanel}
          aria-controls="hdr-suggest"
        />
        {/* กำลังค้น: วงหมุนเล็กๆ ให้รู้ว่าระบบทำงานอยู่ ไม่ใช่ค้างหรือไม่มีของ */}
        {busy && <span className="hdr-search-spin" role="status" aria-label={t("กำลังค้นหา")} />}
        {q && !busy && (
          <button type="button" className="hdr-search-clear" aria-label="ล้างคำค้น" onClick={() => { setQ(""); setData(null); }}>
            <Icon name="close" size={18} />
          </button>
        )}
        <button type="submit" className="hdr-search-go" aria-label="ค้นหา"><Icon name="search" size={20} /></button>
      </form>

      {showPanel && discover && (
        <div className="hdr-suggest sug-discover" id="hdr-suggest" role="listbox">
          <div className="sug-col">
            <div className="sug-head"><span>ค้นหาตามหมวดหมู่</span></div>
            <div className="sug-cats">
              {cats.map((c) => (
                <button key={c.label} className="sug-cat" onClick={() => go(c.href!, c.label)}>
                  <Icon name={catIcon(c.label)} size={18} />
                  <span>{c.label}</span>
                </button>
              ))}
            </div>

            {showRecent && (
              <>
                <div className="sug-head">
                  <span>ค้นหาล่าสุด</span>
                  <button className="link-btn small" onClick={() => { localStorage.removeItem(RECENT_KEY); setRecent([]); }}>ล้างทั้งหมด</button>
                </div>
                <div className="sug-chips">
                  {recent.map((term, i) => (
                    <span key={term} className={"sug-chip" + (cursor === i ? " on" : "")} onMouseEnter={() => setCursor(i)}>
                      <button onClick={() => submit(term)}>{term}</button>
                      {/* ลบทีละคำ — คำที่พิมพ์ผิดหรือรหัสที่ค้นครั้งเดียวจะได้ไม่ค้างอยู่ */}
                      <button className="x" aria-label={`ลบ ${term}`} onClick={() => setRecent(forgetSearch(term))}>
                        <Icon name="close" size={14} />
                      </button>
                    </span>
                  ))}
                </div>
              </>
            )}

            <div className="sug-head"><span>ค้นหาตามงบ</span></div>
            <div className="sug-chips">
              {BUDGETS.map((b) => (
                <button key={b.label} className="sug-chip budget" onClick={() => go(b.href, b.label)}>{b.label}</button>
              ))}
            </div>
          </div>

          {best.length > 0 && (
            <div className="sug-col sug-best">
              <div className="sug-head"><span>สินค้าขายดี</span></div>
              {best.map((m) => (
                <button key={m.matnr} className="sug-item" onClick={() => go(`/p/${m.matnr}`, m.name_th)}>
                  <Placeholder src={imageSources(m.matnr, m.image_url)} className="sug-thumb" label="" />
                  <span className="sug-name">
                    {/* ต้องห่อชื่อด้วย span — กฎตัดบรรทัดชื่อยิงที่ลูกตัวแรก ถ้าปล่อยชื่อเป็น
                        text node เฉยๆ ลูกตัวแรกจะกลายเป็นบรรทัดราคา แล้วราคาจะโดนตัดแทน */}
                    <span className="sug-title">{m.name_th}</span>
                    <small className="sug-price">
                      <b>฿{Number(m.price).toLocaleString()}</b>
                      {m.compare_at_price ? <s>฿{Number(m.compare_at_price).toLocaleString()}</s> : null}
                      {m.discount_percent ? <i>ลด {m.discount_percent}%</i> : null}
                    </small>
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {showPanel && !discover && (
        <div className="hdr-suggest" id="hdr-suggest" role="listbox">
          {rows.slice(0, tips.length).map((r, i) => (
            <button
              key={`t-${r.label}-${i}`}
              className={"sug-row" + (cursor === i ? " on" : "")}
              role="option"
              aria-selected={cursor === i}
              onMouseEnter={() => setCursor(i)}
              onClick={r.go}
            >
              <Icon name="search" size={18} />
              <span>{r.label}</span>
            </button>
          ))}
          {products.length > 0 && (
            <>
              <div className="sug-head"><span>สินค้าที่ตรงที่สุด</span></div>
              {products.map((m, i) => {
                const idx = tips.length + i;
                return (
                  <button
                    key={m.matnr}
                    className={"sug-item" + (cursor === idx ? " on" : "")}
                    role="option"
                    aria-selected={cursor === idx}
                    onMouseEnter={() => setCursor(idx)}
                    onClick={() => go(`/p/${m.matnr}`, q)}
                  >
                    <Placeholder src={imageSources(m.matnr, m.image_url)} className="sug-thumb" label="" />
                    <span className="sug-name">
                      {m.name_th}
                      <small>{m.matnr}{m.brand_name ? ` · ${m.brand_name}` : ""}</small>
                    </span>
                    <b>{Number(m.price).toLocaleString()}.-</b>
                  </button>
                );
              })}
              <button className="sug-all" onClick={() => submit(q)}>ดูผลทั้งหมดของ “{q.trim()}”</button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
