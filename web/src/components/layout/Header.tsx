import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import { useContent } from "../../lib/content";
import { areaLabel, getProvinces, lookupPostcode } from "../../lib/geo";
import type { Province } from "../../lib/types";
import Icon from "../Icon";

export default function Header({ cartCount = 0, cartHref = "/cart" }: { cartCount?: number; cartHref?: string }) {
  const auth = useAuth();
  const { content, plants, plant, setPlantCode, postcode, shipTo, setShipTo } = useContent();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [menu, setMenu] = useState<string | null>(null);
  const [sideIdx, setSideIdx] = useState(0);
  const [pop, setPop] = useState<"address" | "branch" | null>(null);
  const [pcDraft, setPcDraft] = useState(postcode);
  const [provinces, setProvinces] = useState<Province[]>([]);
  const [provQ, setProvQ] = useState("");
  const [pcErr, setPcErr] = useState<string | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  // โหลดรายชื่อจังหวัดตอนเปิด popup ครั้งแรก (แคชไว้ใน lib/geo แล้ว เปิดซ้ำไม่ยิงใหม่)
  useEffect(() => {
    if (pop !== "address") return;
    getProvinces().then(setProvinces).catch(() => setProvinces([]));
  }, [pop]);

  const pickProvince = (p: Province) => {
    setShipTo({ province_id: p.province_id, name_th: p.name_th, area_id: p.area_id, postcode: p.postcode, exact: false });
    setPcDraft(p.postcode);
    setPcErr(null);
    setPop(null);
  };

  // กรอกรหัสไปรษณีย์เอง = แม่นกว่าจังหวัดตัวแทน — ไล่ย้อนหาจังหวัดให้เลย
  const useDraftPostcode = async () => {
    const pc = pcDraft.trim();
    setPcErr(null);
    const hits = await lookupPostcode(pc);
    if (!hits.length) return setPcErr("ไม่พบรหัสไปรษณีย์นี้ — เลือกจังหวัดจากรายการด้านล่างได้");
    const h = hits[0];
    setShipTo({ province_id: h.province_id, name_th: h.province_th, area_id: h.area_id, postcode: pc, exact: true });
    setPop(null);
  };

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
  const openDef = mainNav.find((n) => n.label === menu && n.items.length > 0);
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
        <Link to="/" className="hdr-logo ph" aria-label="SB Design Square">
          <img src="https://media.sbdesignsquare.com/media/logo/stores/2/Logo_header_newsb_1.png" alt="SB Design Square" />
        </Link>

        <div className="hdr-locs">
          <button className="hdr-loc" onClick={() => { setPop(pop === "address" ? null : "address"); setPcDraft(postcode); }}>
            <small>ที่อยู่จัดส่ง</small>
            <span><Icon name="location_on" size={18} /> {shipTo ? `${shipTo.name_th} ${shipTo.postcode}` : postcode ? `รหัสไปรษณีย์ ${postcode}` : "เลือกที่อยู่จัดส่ง"} <Icon name="expand_more" size={16} /></span>
          </button>
          <span className="hdr-loc-sep" />
          <button className="hdr-loc" onClick={() => setPop(pop === "branch" ? null : "branch")}>
            <small>รับที่สาขา</small>
            <span><Icon name="storefront" size={18} /> {plant ? plant.name : "เลือกสาขา"} <Icon name="expand_more" size={16} /></span>
          </button>
          {pop === "address" && (
            <div className="hdr-pop">
              <div className="strong" style={{ marginBottom: 6 }}>ส่งไปที่จังหวัดไหน</div>
              {/* ค่าส่งขึ้นกับเขต (กทม.+ปริมณฑล / ต่างจังหวัด) ซึ่งรู้ได้ตั้งแต่รู้จังหวัด
                  เลยให้เลือกจังหวัดคร่าวๆ ก่อน แล้วค่อยกรอกที่อยู่เต็มตอน checkout */}
              <p className="muted small" style={{ margin: "0 0 8px" }}>เลือกจังหวัดเพื่อดูค่าส่งคร่าวๆ · ที่อยู่เต็มค่อยกรอกตอนสั่งซื้อ</p>
              <form className="row" onSubmit={(e) => { e.preventDefault(); void useDraftPostcode(); }}>
                <input className="hdr-pop-input" value={pcDraft} onChange={(e) => { setPcDraft(e.target.value.replace(/\D/g, "").slice(0, 5)); setPcErr(null); }} placeholder="รู้รหัสไปรษณีย์ พิมพ์ได้เลย" inputMode="numeric" maxLength={5} />
                <button className="btn dark sm" type="submit" disabled={pcDraft.trim().length !== 5}>ใช้</button>
              </form>
              {pcErr && <div className="note err small" style={{ marginTop: 6 }}>{pcErr}</div>}
              {auth.user?.default_postcode && (
                <button className="link-btn small" style={{ marginTop: 6 }} onClick={() => { setPcDraft(auth.user!.default_postcode!); void useDraftPostcode(); }}>
                  ใช้ที่อยู่หลัก · {auth.user.default_address} {auth.user.default_postcode}
                </button>
              )}
              <input className="hdr-pop-input" style={{ width: "100%", marginTop: 8 }} value={provQ} onChange={(e) => setProvQ(e.target.value)} placeholder="ค้นหาจังหวัด" />
              <div className="hdr-pop-list">
                {provinces
                  .filter((p) => !provQ.trim() || p.name_th.includes(provQ.trim()) || (p.name_en || "").toLowerCase().includes(provQ.trim().toLowerCase()))
                  .map((p) => (
                    <button key={p.province_id} className={"hdr-pop-row" + (shipTo?.province_id === p.province_id ? " on" : "")} onClick={() => pickProvince(p)}>
                      <Icon name="place" size={18} />
                      <span><b>{p.name_th}</b><small>{areaLabel(p.area_id)}{p.serviceable ? "" : " · บางพื้นที่รถส่งไม่ถึง"}</small></span>
                    </button>
                  ))}
                {provinces.length === 0 && <div className="muted small">กำลังโหลดรายชื่อจังหวัด…</div>}
              </div>
              {shipTo && (
                <div className="small muted" style={{ marginTop: 8 }}>
                  ตอนนี้คิดค่าส่งแบบ{areaLabel(shipTo.area_id)} · {shipTo.exact ? `รหัส ${shipTo.postcode}` : `ประเมินจากรหัส ${shipTo.postcode}`}
                  <button className="link-btn small" style={{ marginLeft: 6 }} onClick={() => { setShipTo(null); setPcDraft(""); setPop(null); }}>ล้าง</button>
                </div>
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

        {/* ช่องค้นหาอยู่กลางแถวเดียวกับโลโก้ ช่องว่างตรงกลางจะได้ไม่โล่ง และไม่ต้องมีแถวแยกอีกแถว */}
        <form className="hdr-search" onSubmit={submitSearch} role="search">
          <span className="hdr-search-all">ทั้งหมด <Icon name="expand_more" size={16} /></span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="ค้นหาสินค้า แบรนด์ หรือห้องที่ต้องการ" aria-label="ค้นหา" />
          <span className="hdr-search-ai"><Icon name="auto_awesome" size={16} /> AI</span>
          <button type="submit" className="hdr-search-go" aria-label="ค้นหา"><Icon name="search" size={20} /></button>
        </form>

        <div className="hdr-icons">
          <button className="icon-btn" aria-label="แจ้งเตือน"><Icon name="notifications" /></button>
          <button className="icon-btn" aria-label="คูปอง"><Icon name="confirmation_number" /></button>
          <Link to="/account/wishlist" className="icon-btn" aria-label="รายการโปรด" title="รายการโปรด"><Icon name="favorite" /></Link>
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
              <Link to="/account" className="hdr-user-link" title="บัญชีของฉัน">
                <Icon name="account_circle" size={26} />
                <span className="hdr-user-txt">
                  <b>{auth.user.name}</b>
                  <small>{roleLabel}</small>
                </span>
              </Link>
              <button className="link-btn small" onClick={() => auth.logout()}>ออก</button>
            </div>
          ) : (
            <>
              <button className="icon-btn hdr-icon-login" onClick={auth.openLogin} aria-label="บัญชี"><Icon name="group" /></button>
              <button className="btn hdr-login-btn" onClick={auth.openLogin}><Icon name="login" size={18} /> เข้าสู่ระบบ</button>
            </>
          )}
        </div>

      </div>

      {/* main nav */}
      <div className="hdr-nav-wrap">
        <nav className="container hdr-nav">
          {/* สินค้าใหม่มาก่อนสุด — เรียงตามของเข้าใหม่ ไม่มีหมวดย่อยเลยไม่มีลูกศร */}
          <Link to="/search?sort=new" className="hdr-nav-item" onClick={() => setMenu(null)}>
           สินค้าใหม่
          </Link>
          {/* กดที่ตัวหนังสือ = ดูสินค้าทั้งหมดเลย · กดลูกศร (หรือชี้ค้าง) = เลือกเฉพาะหมวด */}
          <div className={"hdr-nav-item cats" + (menu === "__cats" ? " on" : "")} onMouseEnter={() => setMenu("__cats")}>
            <Link to="/search" className="cats-all" onClick={() => setMenu(null)}>
              <Icon name="grid_view" size={20} /> สินค้าทั้งหมด
            </Link>
            <button
              className="cats-toggle"
              onClick={() => setMenu(menu === "__cats" ? null : "__cats")}
              aria-label="เลือกหมวดสินค้า"
              aria-expanded={menu === "__cats"}
            >
              <Icon name="expand_more" size={16} />
            </button>
          </div>
          {/* เหมือนช่อง "สินค้าทั้งหมด": กดตัวหนังสือ = เข้าหมวดกลุ่มนั้นเลย · กดลูกศร = เลือกหมวดย่อย */}
          {mainNav.map((n) => (
            <div key={n.label} className={"hdr-nav-item cats" + (menu === n.label ? " on" : "")} onMouseEnter={() => setMenu(n.label)}>
              {n.href ? (
                <Link to={n.href} className="cats-all" onClick={() => setMenu(null)}>{n.label}</Link>
              ) : (
                <span className="cats-all">{n.label}</span>
              )}
              {n.items.length > 0 && (
                <button className="cats-toggle" onClick={() => setMenu(menu === n.label ? null : n.label)} aria-label={`หมวดย่อยของ ${n.label}`} aria-expanded={menu === n.label}>
                  <Icon name="expand_more" size={16} />
                </button>
              )}
            </div>
          ))}
        </nav>

        {menu === "__cats" && (
          <div className="mega" onMouseLeave={() => setMenu(null)}>
            <div className="container mega-in">
              <ul className="mega-side">
                <li className={sideIdx === -1 ? "on" : ""} onMouseEnter={() => setSideIdx(-1)}>
                  <Link to="/search" onClick={() => setMenu(null)}>ดูสินค้าทั้งหมด</Link>
                </li>
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
