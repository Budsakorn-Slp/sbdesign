import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import { useContent } from "../../lib/content";
import { localName, useLang } from "../../lib/i18n";
import { areaLabel, getProvinces, lookupPostcode } from "../../lib/geo";
import type { Province } from "../../lib/types";
import Icon from "../Icon";
import SearchBox from "../SearchBox";

export default function Header({ cartCount = 0, cartHref = "/cart" }: { cartCount?: number; cartHref?: string }) {
  const auth = useAuth();
  const { lang, setLang, t } = useLang();
  const { content, plants, plant, setPlantCode, postcode, shipTo, setShipTo } = useContent();
  const [menu, setMenu] = useState<string | null>(null);
  // -1 = โชว์หมวดทั้งหมด · เลขอื่น = โชว์หมวดย่อยของห้องนั้น (เปลี่ยนตอนชี้ค้างที่รายชื่อด้านซ้าย)
  // ต้องเริ่มที่ -1 เพราะจอแคบซ่อนรายชื่อด้านซ้ายไว้ ชี้ค้างไม่ได้ ถ้าเริ่มที่ 0 เมนู
  // "สินค้าทั้งหมด" บนมือถือจะค้างโชว์แค่หมวดย่อยของห้องแรกตลอด ไม่มีทางไปห้องอื่น
  const [sideIdx, setSideIdx] = useState(-1);
  const [pop, setPop] = useState<"address" | "branch" | null>(null);
  const [pcDraft, setPcDraft] = useState(postcode);
  const [provinces, setProvinces] = useState<Province[]>([]);
  const [provQ, setProvQ] = useState("");
  const [pcErr, setPcErr] = useState<string | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [shrink, setShrink] = useState(false);

  // หัวเว็บติดขอบบนตลอด (position: sticky) พอเลื่อนลงจะย่อให้เตี้ยลง
  // เหลือโลโก้ + ช่องค้นหา + แถบเมนู เพื่อไม่ให้กินจอเกินไป
  // เข้า-ออกคนละระยะ (80/40) กันหัวกระพริบตอนเลื่อนค้างอยู่ตรงเส้นพอดี
  useEffect(() => {
    const onScroll = () => {
      // ต้องอ่านค่าตรงนี้ก่อน — ถ้าไปอ่านข้างใน setShrink React อาจเรียกทีหลัง
      // ตอนที่เลื่อนไปไกลแล้ว หัวเว็บจะค้างย่ออยู่ทั้งที่กลับขึ้นบนสุดแล้ว
      const y = window.scrollY;
      setShrink((on) => (on ? y > 40 : y > 80));
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

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

  const cats = content?.categories || [];
  const brands = content?.brands || [];
  const mainNav = content?.main_nav || [];
  const openDef = mainNav.find((n) => n.label === menu && (n.items.length > 0 || (n.groups?.length ?? 0) > 0));
  const roleLabel = auth.user
    ? auth.user.role === "customer"
      ? `${t("สมาชิก")} · ${(auth.user.points || 0).toLocaleString()} ${t("พ้อยท์")}`
      : auth.user.role === "sales"
        ? `${t("พนักงานขาย")} · ${auth.user.staff_code}`
        : auth.user.role === "manager"
          ? `${t("ผู้จัดการ")} · ${auth.user.staff_code}`
          : t("แอดมิน")
    : "";

  return (
    <header className={"hdr" + (shrink ? " shrink" : "")} ref={wrapRef}>
      {/* util bar */}
      <div className="hdr-util">
        <div className="container hdr-util-in">
          <span className="hdr-free">{lang === "en" ? "Free delivery over 3,000.-" : content?.free_shipping_note || "ส่งฟรีเมื่อช้อปครบ 3,000.-"}</span>
          <nav className="hdr-util-links">
            <a href="#"><Icon name="credit_card" size={18} /> SB Member Card</a>
            <a href="#"><Icon name="location_on" size={18} /> {t("ค้นหาสาขา")}</a>
            <a href="#"><Icon name="support_agent" size={18} /> {t("ศูนย์ช่วยเหลือ")} <Icon name="expand_more" size={16} /></a>
            {/* สลับภาษาจริง — จำค่าไว้ใน localStorage และตั้ง <html lang> ให้เบราว์เซอร์รู้ด้วย */}
            <span className="hdr-lang">
              <button type="button" className={lang === "th" ? "on" : ""} onClick={() => setLang("th")}>TH</button>
              <i>|</i>
              <button type="button" className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>EN</button>
            </span>
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
            <small>{t("ที่อยู่จัดส่ง")}</small>
            <span><Icon name="location_on" size={18} /> {shipTo ? `${shipTo.name_th} ${shipTo.postcode}` : postcode ? `${t("รหัสไปรษณีย์")} ${postcode}` : t("เลือกที่อยู่จัดส่ง")} <Icon name="expand_more" size={16} /></span>
          </button>
          <span className="hdr-loc-sep" />
          <button className="hdr-loc" onClick={() => setPop(pop === "branch" ? null : "branch")}>
            <small>{t("รับที่สาขา")}</small>
            <span><Icon name="storefront" size={18} /> {plant ? plant.name : t("เลือกสาขา")} <Icon name="expand_more" size={16} /></span>
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
                  <Icon name="storefront" size={18} /> <span><b>{p.name}</b>{p.address && <small>{p.address}</small>}</span>
                </button>
              ))}
              {plant && <button className="link-btn small" onClick={() => { setPlantCode(null); setPop(null); }}>{t("ไม่เลือกสาขา")}</button>}
            </div>
          )}
        </div>

        {/* ช่องค้นหาอยู่กลางแถวเดียวกับโลโก้ ช่องว่างตรงกลางจะได้ไม่โล่ง และไม่ต้องมีแถวแยกอีกแถว */}
        <SearchBox onNavigate={() => setMenu(null)} />

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
              <Link to="/account" className="hdr-user-link" title={t("บัญชีของฉัน")}>
                <Icon name="account_circle" size={26} />
                <span className="hdr-user-txt">
                  <b>{auth.user.name}</b>
                  <small>{roleLabel}</small>
                </span>
              </Link>
              <button className="link-btn small" onClick={() => auth.logout()}>{t("ออก")}</button>
            </div>
          ) : (
            <>
              <button className="icon-btn hdr-icon-login" onClick={auth.openLogin} aria-label={t("เข้าสู่ระบบ")}><Icon name="group" /></button>
              <button className="btn hdr-login-btn" onClick={auth.openLogin}><Icon name="login" size={18} /> {t("เข้าสู่ระบบ")}</button>
            </>
          )}
        </div>

      </div>

      {/* main nav */}
      <div className="hdr-nav-wrap">
        <nav className="container hdr-nav">
          {/* ปลายทางเดียวกับการกดโลโก้ — คนที่หลงอยู่กลางหน้าค้นหาจะได้มีทางกลับที่เห็นชัดๆ
              ไม่ต้องเดาว่าต้องกดโลโก้ */}
          <Link to="/" className="hdr-nav-item" onClick={() => setMenu(null)}>
            {t("หน้าแรก")}
          </Link>
          {/* กดที่ตัวหนังสือ = ดูสินค้าทั้งหมดเลย · กดลูกศร (หรือชี้ค้าง) = เลือกเฉพาะหมวด */}
          <div className={"hdr-nav-item cats" + (menu === "__cats" ? " on" : "")} onMouseEnter={() => setMenu("__cats")}>
            <Link to="/search" className="cats-all" onClick={() => setMenu(null)}>
              <Icon name="grid_view" size={20} /> {t("สินค้าทั้งหมด")}
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
          {/* แบรนด์ — กดตัวหนังสือ = ไปหน้าสินค้าทั้งหมด · กดลูกศร = เลือกแบรนด์
              รายชื่อมาจาก content.brands ซึ่ง backend กรองเหลือเฉพาะแบรนด์ที่มีของขายอยู่จริง
              พร้อมจำนวน กดเข้าไปจึงไม่มีทางเจอหน้าว่าง */}
          {brands.length > 0 && (
            <div className={"hdr-nav-item cats" + (menu === "__brands" ? " on" : "")} onMouseEnter={() => setMenu("__brands")}>
              <Link to="/search" className="cats-all" onClick={() => setMenu(null)}>{t("แบรนด์")}</Link>
              <button
                className="cats-toggle"
                onClick={() => setMenu(menu === "__brands" ? null : "__brands")}
                aria-label="เลือกแบรนด์"
                aria-expanded={menu === "__brands"}
              >
                <Icon name="expand_more" size={16} />
              </button>
            </div>
          )}
          {/* เหมือนช่อง "สินค้าทั้งหมด": กดตัวหนังสือ = เข้าหมวดกลุ่มนั้นเลย · กดลูกศร = เลือกหมวดย่อย */}
          {mainNav.map((n) => (
            <div key={n.label} className={"hdr-nav-item cats" + (menu === n.label ? " on" : "")} onMouseEnter={() => setMenu(n.label)}>
              {n.href ? (
                <Link to={n.href} className="cats-all" onClick={() => setMenu(null)}>{localName(lang, n.label, n.label_en)}</Link>
              ) : (
                <span className="cats-all">{localName(lang, n.label, n.label_en)}</span>
              )}
              {(n.items.length > 0 || (n.groups?.length ?? 0) > 0) && (
                <button className="cats-toggle" onClick={() => setMenu(menu === n.label ? null : n.label)} aria-label={`${t("หมวดย่อยของ")} ${localName(lang, n.label, n.label_en)}`} aria-expanded={menu === n.label}>
                  <Icon name="expand_more" size={16} />
                </button>
              )}
            </div>
          ))}
        </nav>

        {menu === "__brands" && (
          <div className="mega" onMouseLeave={() => setMenu(null)}>
            <div className="container mega-in one-col">
              <div className="mega-body">
                <div className="mega-title">{t("แบรนด์ทั้งหมด")}</div>
                <div className="mega-grid brand-grid">
                  {brands.map((b) => (
                    <Link key={b.id} to={`/search?brand=${encodeURIComponent(b.id)}`} className="mega-item brand-item" onClick={() => setMenu(null)}>
                      {b.name}
                    </Link>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
        {menu === "__cats" && (
          <div className="mega" onMouseLeave={() => setMenu(null)}>
            <div className="container mega-in">
              <ul className="mega-side">
                <li className={sideIdx === -1 ? "on" : ""} onMouseEnter={() => setSideIdx(-1)}>
                  <Link to="/search" onClick={() => setMenu(null)}>{t("ดูสินค้าทั้งหมด")}</Link>
                </li>
                {/* ของเข้าใหม่ = ชั้น N ของ MAABC ที่ฝ่ายสินค้าจัดไว้ ไม่ใช่เรียงตามวันที่สร้างรหัส
                    (วันที่สร้างรหัสไม่ได้แปลว่าของเพิ่งเข้าร้าน) · ไม่มีหมวดย่อย ชี้ค้างแล้ว
                    จึงคงแผงขวาเป็นหมวดทั้งหมดไว้เหมือนเดิม (sideIdx -1) */}
                <li className="" onMouseEnter={() => setSideIdx(-1)}>
                  <Link to="/search?abc=N" onClick={() => setMenu(null)}>{t("สินค้าใหม่")}</Link>
                </li>
                {cats.map((c, i) => (
                  <li key={c.id} className={sideIdx === i ? "on" : ""} onMouseEnter={() => setSideIdx(i)}>
                    <Link to={`/search?category=${c.id}`} onClick={() => setMenu(null)}>{localName(lang, c.name_th, c.name_en)}</Link>
                  </li>
                ))}
              </ul>
              <div className="mega-body">
                {sideIdx >= 0 && cats[sideIdx] && cats[sideIdx].children.length > 0 ? (
                  <>
                    <div className="mega-title">{localName(lang, cats[sideIdx].name_th, cats[sideIdx].name_en)}</div>
                    <div className="mega-grid">
                      {cats[sideIdx].children.map((ch) => (
                        <Link key={ch.id} to={`/search?category=${ch.id}`} className="mega-item" onClick={() => setMenu(null)}>
                          <span className="mega-ico"><Icon name={cats[sideIdx].icon || "category"} size={26} /></span>
                          {localName(lang, ch.name_th, ch.name_en)}
                        </Link>
                      ))}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="mega-title">{t("หมวดหมู่ทั้งหมด")}</div>
                    <div className="mega-grid">
                      {cats.map((c) => (
                        <Link key={c.id} to={`/search?category=${c.id}`} className="mega-item" onClick={() => setMenu(null)}>
                          <span className="mega-ico"><Icon name={c.icon || "category"} size={26} /></span>
                          {localName(lang, c.name_th, c.name_en)}
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
              {openDef.groups?.length ? (
                /* เมนู 3 ชั้นแบบเว็บจริง — หัวกลุ่มกดไปหน้าหมวดกลุ่มได้ ข้างใต้เป็นหมวดย่อย
                   จัดเป็นคอลัมน์แบบ masonry ให้กลุ่มไหลต่อกันเอง ไม่ต้องกำหนดว่ากลุ่มไหนอยู่คอลัมน์ไหน */
                <div className="nav-groups">
                  {openDef.groups.map((g) => (
                    <div key={g.label} className="nav-group">
                      <Link to={g.href} className="nav-group-head" onClick={() => setMenu(null)}>
                        {localName(lang, g.label, g.label_en)} <Icon name="arrow_forward" size={16} />
                      </Link>
                      <ul>
                        {g.items.map((it) => (
                          <li key={it.label}>
                            <Link to={it.href} onClick={() => setMenu(null)}>{localName(lang, it.label, it.label_en)}</Link>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              ) : (
                <>
                  <div className="mega-title">{localName(lang, openDef.label, openDef.label_en)}</div>
                  <ul className="sub-list">
                    {openDef.items.map((it) => (
                      <li key={it.label}>
                        <Link to={it.href} onClick={() => setMenu(null)}>{localName(lang, it.label, it.label_en)}</Link>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
