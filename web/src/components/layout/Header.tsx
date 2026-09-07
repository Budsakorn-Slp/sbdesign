import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import { useContent } from "../../lib/content";
import Icon from "../Icon";

export default function Header({ cartCount = 0, cartHref = "/cart" }: { cartCount?: number; cartHref?: string }) {
  const auth = useAuth();
  const { content, plants, plant, setPlantCode, postcode, setPostcode } = useContent();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [menu, setMenu] = useState<string | null>(null);
  const [sideIdx, setSideIdx] = useState(0);
  const [pop, setPop] = useState<"address" | "branch" | null>(null);
  const [pcDraft, setPcDraft] = useState(postcode);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setMenu(null);
        setPop(null);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const submitSearch = (e: FormEvent) => {
    e.preventDefault();
    setMenu(null);
    nav(q.trim() ? `/search?q=${encodeURIComponent(q.trim())}` : "/search");
  };

  const cats = content?.categories || [];
  const mainNav = content?.main_nav || [];
  const openDef = mainNav.find((n) => n.label === menu);
  const roleLabel = auth.user
    ? auth.user.role === "customer"
      ? `สมาชิก ${auth.user.tier || ""}`.trim()
      : auth.user.role === "sales"
        ? `พนักงานขาย · ${auth.user.staff_code}`
        : auth.user.role === "manager"
          ? `ผู้จัดการ · ${auth.user.staff_code}`
          : "แอดมิน"
    : "";

  return (
    <header className="hdr" ref={wrapRef}>
      {/* util bar */}
      <div className="hdr-util">
        <div className="container hdr-util-in">
          <span className="hdr-free">{content?.free_shipping_note || "ส่งฟรีเมื่อช้อปครบ 3,000.-"}</span>
          <nav className="hdr-util-links">
            <a href="#"><Icon name="credit_card" size={18} /> SB Member Card</a>
            <a href="#"><Icon name="location_on" size={18} /> ค้นหาสาขา</a>
            <a href="#"><Icon name="support_agent" size={18} /> ศูนย์ช่วยเหลือ <Icon name="expand_more" size={16} /></a>
            <span className="hdr-lang"><b>TH</b> | EN</span>
          </nav>
        </div>
      </div>

      {/* main row */}
      <div className="container hdr-main">
        <Link to="/" className="hdr-logo ph" aria-label="SB Design Square">SB&nbsp;&nbsp;LOGO</Link>

        <div className="hdr-locs">
          <button className="hdr-loc" onClick={() => { setPop(pop === "address" ? null : "address"); setPcDraft(postcode); }}>
            <small>ที่อยู่จัดส่ง</small>
            <span><Icon name="location_on" size={18} /> {postcode ? `รหัสไปรษณีย์ ${postcode}` : "เลือกที่อยู่จัดส่ง"} <Icon name="expand_more" size={16} /></span>
          </button>
          <span className="hdr-loc-sep" />
          <button className="hdr-loc" onClick={() => setPop(pop === "branch" ? null : "branch")}>
            <small>รับที่สาขา</small>
            <span><Icon name="storefront" size={18} /> {plant ? plant.name : "เลือกสาขา"} <Icon name="expand_more" size={16} /></span>
          </button>
          {pop === "address" && (
            <div className="hdr-pop">
              <div className="strong" style={{ marginBottom: 6 }}>ที่อยู่จัดส่ง</div>
              <p className="muted small" style={{ margin: "0 0 8px" }}>กรอกรหัสไปรษณีย์เพื่อคำนวณค่าส่งและคิวจัดส่ง</p>
              <form className="row" onSubmit={(e) => { e.preventDefault(); setPostcode(pcDraft.trim()); setPop(null); }}>
                <input className="hdr-pop-input" value={pcDraft} onChange={(e) => setPcDraft(e.target.value)} placeholder="เช่น 10110" inputMode="numeric" maxLength={5} />
                <button className="btn dark sm" type="submit">ใช้</button>
              </form>
              {auth.user?.default_postcode && (
                <button className="link-btn small" style={{ marginTop: 6 }} onClick={() => { setPostcode(auth.user!.default_postcode!); setPop(null); }}>
                  ใช้ที่อยู่หลัก · {auth.user.default_address} {auth.user.default_postcode}
                </button>
              )}
            </div>
          )}
          {pop === "branch" && (
            <div className="hdr-pop">
              <div className="strong" style={{ marginBottom: 6 }}>รับที่สาขา</div>
              {plants.filter((p) => p.type === "store").map((p) => (
                <button key={p.plant_code} className={"hdr-pop-row" + (plant?.plant_code === p.plant_code ? " on" : "")} onClick={() => { setPlantCode(p.plant_code); setPop(null); }}>
                  <Icon name="storefront" size={18} /> <span><b>{p.name}</b><small>{p.address}</small></span>
                </button>
              ))}
              {plant && <button className="link-btn small" onClick={() => { setPlantCode(null); setPop(null); }}>ไม่เลือกสาขา</button>}
            </div>
          )}
        </div>

        <div className="hdr-icons">
          <button className="icon-btn" aria-label="แจ้งเตือน"><Icon name="notifications" /></button>
          <button className="icon-btn" aria-label="คูปอง"><Icon name="confirmation_number" /></button>
          <Link to={cartHref} className="icon-btn" aria-label="ตะกร้า">
            <Icon name="shopping_cart" />
            {cartCount > 0 && <span className="badge">{cartCount}</span>}
          </Link>
          {auth.user && (auth.user.role === "manager" || auth.user.role === "admin") && (
            <>
              <Link to="/manager/approvals" className="icon-btn" aria-label="อนุมัติส่วนลด" title="คำขออนุมัติส่วนลด"><Icon name="approval" /></Link>
              <Link to="/manager/sap-sync" className="icon-btn" aria-label="คิวส่ง SAP" title="คิวส่งข้อมูลเข้า SAP"><Icon name="sync_problem" /></Link>
            </>
          )}
          {auth.user ? (
            <div className="hdr-user">
              <Icon name="account_circle" size={26} />
              <span className="hdr-user-txt">
                <b>{auth.user.name}</b>
                <small>{roleLabel}</small>
              </span>
              <button className="link-btn small" onClick={() => auth.logout()}>ออก</button>
            </div>
          ) : (
            <>
              <button className="icon-btn hdr-icon-login" onClick={auth.openLogin} aria-label="บัญชี"><Icon name="group" /></button>
              <button className="btn hdr-login-btn" onClick={auth.openLogin}><Icon name="login" size={18} /> เข้าสู่ระบบ</button>
            </>
          )}
        </div>

        <form className="hdr-search" onSubmit={submitSearch} role="search">
          <span className="hdr-search-all">ทั้งหมด <Icon name="expand_more" size={16} /></span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="ค้นหาสินค้า แบรนด์ หรือห้องที่ต้องการ" aria-label="ค้นหา" />
          <button type="submit" className="hdr-search-ai"><Icon name="auto_awesome" size={16} /> AI</button>
        </form>
      </div>

      {/* main nav */}
      <div className="hdr-nav-wrap">
        <nav className="container hdr-nav">
          <button className={"hdr-nav-item cats" + (menu === "__cats" ? " on" : "")} onClick={() => setMenu(menu === "__cats" ? null : "__cats")}>
            <Icon name="grid_view" size={20} /> เลือกหมวดสินค้า <Icon name="expand_more" size={16} />
          </button>
          {mainNav.map((n) => (
            <button key={n.label} className={"hdr-nav-item" + (menu === n.label ? " on" : "")} onMouseEnter={() => setMenu(n.label)} onClick={() => setMenu(menu === n.label ? null : n.label)}>
              {n.label} <Icon name="expand_more" size={16} />
            </button>
          ))}
        </nav>

        {menu === "__cats" && (
          <div className="mega" onMouseLeave={() => setMenu(null)}>
            <div className="container mega-in">
              <ul className="mega-side">
                <li className={sideIdx === -1 ? "on" : ""} onMouseEnter={() => setSideIdx(-1)}>หมวดหมู่ทั้งหมด</li>
                {cats.map((c, i) => (
                  <li key={c.id} className={sideIdx === i ? "on" : ""} onMouseEnter={() => setSideIdx(i)}>
                    <Link to={`/search?category=${c.id}`} onClick={() => setMenu(null)}>{c.name_th}</Link>
                  </li>
                ))}
              </ul>
              <div className="mega-body">
                {sideIdx >= 0 && cats[sideIdx] && cats[sideIdx].children.length > 0 ? (
                  <>
                    <div className="mega-title">{cats[sideIdx].name_th}</div>
                    <div className="mega-grid">
                      {cats[sideIdx].children.map((ch) => (
                        <Link key={ch.id} to={`/search?category=${ch.id}`} className="mega-item" onClick={() => setMenu(null)}>
                          <span className="mega-ico"><Icon name={cats[sideIdx].icon || "category"} size={26} /></span>
                          {ch.name_th}
                        </Link>
                      ))}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="mega-title">หมวดหมู่ทั้งหมด</div>
                    <div className="mega-grid">
                      {cats.map((c) => (
                        <Link key={c.id} to={`/search?category=${c.id}`} className="mega-item" onClick={() => setMenu(null)}>
                          <span className="mega-ico"><Icon name={c.icon || "category"} size={26} /></span>
                          {c.name_th}
                        </Link>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {openDef && (
          <div className="mega sub" onMouseLeave={() => setMenu(null)}>
            <div className="container">
              <div className="mega-title">{openDef.label}</div>
              <ul className="sub-list">
                {openDef.items.map((it) => (
                  <li key={it.label}>
                    <Link to={it.href} onClick={() => setMenu(null)}>{it.label}</Link>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
