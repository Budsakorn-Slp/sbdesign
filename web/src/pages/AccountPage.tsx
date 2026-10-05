import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import AddressBook from "../components/AddressBook";
import Icon from "../components/Icon";
import MemberLink from "../components/MemberLink";
import ProductCard from "../components/ProductCard";
import { apiGet, apiPatch, apiPost, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useWishlist } from "../lib/wishlist";
import { baht } from "../lib/format";
import { timeLeftText, usePendingPayments } from "../lib/pending";
import type { MaterialCard, OrderHistory } from "../lib/types";

const TABS = [
  // ของที่ "ต้องทำอะไรต่อ" มาก่อนของที่ดูย้อนหลัง · ซ่อนเองเมื่อไม่มีรายการค้าง
  { key: "pending", label: "รอชำระเงิน", icon: "pending_actions" },
  { key: "orders", label: "ประวัติการสั่งซื้อ", icon: "receipt_long" },
  { key: "profile", label: "ข้อมูลส่วนตัว", icon: "person" },
  { key: "addresses", label: "ที่อยู่จัดส่ง", icon: "location_on" },
  { key: "wishlist", label: "รายการโปรด", icon: "favorite" },
  { key: "recent", label: "ดูล่าสุด", icon: "history" },
  { key: "privacy", label: "ความเป็นส่วนตัว", icon: "shield_person" },
] as const;

const STATUS_LABEL: Record<string, string> = {
  confirmed: "ยืนยันแล้ว",
  in_production: "กำลังผลิต",
  shipping: "กำลังจัดส่ง",
  delivered: "ส่งสำเร็จ",
  cancelled: "ยกเลิก",
};

function OrderRow({ o }: { o: OrderHistory }) {
  const [open, setOpen] = useState(false);
  return (
    <article className={"order-card" + (open ? " open" : "")}>
      <button className="order-head" onClick={() => setOpen(!open)}>
        <div>
          <div className="order-no mono">{o.so_no}</div>
          <div className="small muted">{o.order_date} · {o.channel === "online" ? "สั่งออนไลน์" : "ที่สาขา"}{o.branch ? ` · ${o.branch}` : ""}</div>
        </div>
        <div className="order-right">
          <span className={"order-status s-" + o.status}>{STATUS_LABEL[o.status] || o.status}</span>
          <strong>{baht(o.grand_total)}</strong>
          <Icon name={open ? "expand_less" : "expand_more"} size={20} />
        </div>
      </button>
      {open && (
        <div className="order-lines">
          {o.lines.map((l) => (
            <div key={l.matnr} className="order-line">
              <Link to={`/p/${l.matnr}`}>{l.name}</Link>
              <span className="muted small">×{l.qty}</span>
              <span>{baht(l.line_total)}</span>
            </div>
          ))}
          {o.delivery_date && <div className="small muted">กำหนดส่ง {o.delivery_date}</div>}
        </div>
      )}
    </article>
  );
}

type Privacy = { consent_marketing: boolean; consent_marketing_at: string | null; anonymized_at: string | null; history: { granted: boolean; source: string; created_at: string }[] };

/** แท็บ "ที่อยู่จัดส่ง" — สมุดที่อยู่ของเรา + ที่อยู่ทะเบียนสมาชิกจาก SAP (ถ้าผูกไว้)
 *
 *  สองอย่างนี้คนละความหมายและต้องไม่ปนกัน:
 *    ทะเบียนสมาชิก (SAP) = ที่อยู่ที่ให้ไว้ตอนสมัครที่สาขา ใช้อ้างอิง/ออกเอกสาร แก้บนเว็บไม่ได้
 *    สมุดที่อยู่จัดส่ง    = ปลายทางที่จะให้ไปส่งของ มีได้หลายที่ ลูกค้าจัดการเองทั้งหมด
 *  สมาชิกที่มีที่อยู่ในทะเบียนอยู่แล้วจึงกด "ใช้ที่อยู่นี้" คัดลอกเข้าสมุดได้ในคลิกเดียว
 */
function AddressPanel() {
  const auth = useAuth();
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const sap = auth.user?.sap_address;

  const copyFromSap = async () => {
    if (!sap) return;
    setBusy(true);
    setErr(null);
    try {
      await apiPost("/me/addresses", {
        label: "ตามทะเบียนสมาชิก",
        receiver: auth.user?.name || "",
        phone: auth.user?.phone || "",
        address: sap,
        postcode: auth.user?.sap_postcode || "",
      });
      setCopied(true);   // remount สมุดที่อยู่ให้โหลดรายการใหม่
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="col" style={{ gap: 14 }}>
      {sap && (
        <section className="card flat">
          <div className="row between wrap" style={{ marginBottom: 6 }}>
            <b><Icon name="badge" size={18} /> ที่อยู่ในทะเบียนสมาชิก</b>
            <span className="small muted">เลขสมาชิก {auth.user?.sap_customer_no}</span>
          </div>
          <div className="small">{sap} {auth.user?.sap_postcode}</div>
          <p className="tiny muted" style={{ margin: "6px 0 10px" }}>
            ที่อยู่นี้มาจากตอนสมัครสมาชิกที่สาขา ใช้อ้างอิงและออกเอกสาร — แก้ไขได้ที่สาขาเท่านั้น
            ส่วนจะให้ส่งของไปที่ไหน เลือกจากสมุดที่อยู่ด้านล่าง
          </p>
          <button className="btn sm" disabled={busy} onClick={copyFromSap}>
            <Icon name="content_copy" size={16} /> {busy ? "กำลังคัดลอก…" : "ใช้ที่อยู่นี้เป็นที่อยู่จัดส่ง"}
          </button>
          {err && <div className="note err small" style={{ marginTop: 8 }}>{err}</div>}
        </section>
      )}

      <section className="card flat">
        <div className="row between wrap" style={{ marginBottom: 6 }}>
          <b><Icon name="local_shipping" size={18} /> สมุดที่อยู่จัดส่ง</b>
          <span className="small muted">เลือกใช้ตอนสั่งซื้อ · ปุ่มกลม = ที่อยู่เริ่มต้น</span>
        </div>
        <AddressBook key={String(copied)} manage selectedId={null} onSelect={() => {}} defaults={{
          receiver: auth.user?.name || "",
          phone: auth.user?.phone || "",
        }} />
      </section>
    </div>
  );
}


function ProfilePanel() {
  const auth = useAuth();
  const u = auth.user;
  // ผูกบัตรสมาชิกแล้ว = ชื่อเป็นของ SAP แก้ที่นี่ไม่ได้ (หลังบ้านก็ปฏิเสธเหมือนกัน)
  const nameLocked = !!u?.sap_customer_no;
  // ค่าเริ่มต้นเป็นโหมดดูอย่างเดียว — กันแก้โดนโดยไม่ตั้งใจ ต้องกด "แก้ไข" ก่อนถึงพิมพ์ได้
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(u?.name || "");
  const [email, setEmail] = useState(u?.email || "");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // auth.user โหลดทีหลัง — ค่าเริ่มต้นตอน render แรกจึงเป็นค่าว่าง ต้องเติมให้ตอนข้อมูลมาถึง
  // ไม่งั้นกดบันทึกแล้วอีเมลเดิมโดนล้างทิ้ง
  useEffect(() => {
    setName(u?.name || "");
    setEmail(u?.email || "");
  }, [u?.id, u?.name, u?.email]);

  if (!u) return <p className="muted">เข้าสู่ระบบเพื่อดูข้อมูลส่วนตัวของคุณ</p>;

  const startEdit = () => {
    setMsg(null);
    setErr(null);
    setEditing(true);
  };

  const cancel = () => {
    setName(u.name);
    setEmail(u.email || "");
    setPw("");
    setErr(null);
    setEditing(false);
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    setErr(null);
    try {
      const body: Record<string, string> = { email: email.trim() };
      if (!nameLocked) body.name = name.trim();
      if (pw) body.password = pw;
      await apiPatch("/me", body);
      await auth.refreshMe();
      setPw("");
      setMsg("บันทึกแล้ว");
      setEditing(false);
    } catch (e2) {
      setErr(errorMessage(e2));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="privacy" onSubmit={save}>
      {/* บัตรสมาชิกอยู่บนสุด — รหัสลูกค้ากับแต้มคือสิ่งที่ลูกค้าเปิดหน้านี้มาดูบ่อยที่สุด
          ส่วนชื่อ/อีเมล/เบอร์ เข้ามาแก้นานๆ ครั้ง */}
      <section className="privacy-box">
        <h2>บัตรสมาชิก</h2>
        {u.sap_customer_no ? (
          <p className="small">แต้มสะสม <b>{u.points.toLocaleString()}</b> พ้อยท์
            <span className="d-block muted">ผูกกับรหัสลูกค้า {u.sap_customer_no}</span>
            <span className="d-block muted">ข้อมูลสมาชิกและแต้มมาจากระบบหลังบ้าน อัปเดตอัตโนมัติ</span>
          </p>
        ) : (
          <p className="small muted">ยังไม่ได้ผูกบัตรสมาชิก — ผูกแล้วจะเห็นแต้มสะสมและประวัติการซื้อจากหน้าร้าน</p>
        )}
      </section>

      <section className="privacy-box">
        <div className="row between" style={{ marginBottom: 12 }}>
          <h2 style={{ margin: 0 }}>ข้อมูลของคุณ</h2>
          {!editing && (
            <button className="btn sm" type="button" onClick={startEdit}>
              <Icon name="edit" size={16} /> แก้ไข
            </button>
          )}
        </div>

        {/* รหัสลูกค้ามาก่อนทุกช่อง — เวลาโทรหาศูนย์บริการหรือคุยกับเซลล์ เขาถามเลขนี้เป็นอย่างแรก
            ของเดิมไปอยู่ท้ายสุดในกล่อง "บัตรสมาชิก" ต้องเลื่อนหาทุกครั้ง
            เลขของ SAP มีหลายชุด (ขึ้นต้น 11 สำหรับลูกค้าทั่วไป · 44 สำหรับสมาชิก) โชว์ตามที่ผูกไว้จริง */}
        <div className={"cust-id" + (u.sap_customer_no ? "" : " none")}>
          <span className="cust-id-lbl"><Icon name="badge" size={16} /> รหัสลูกค้า (CUST ID)</span>
          {u.sap_customer_no ? (
            <b className="mono">{u.sap_customer_no}</b>
          ) : (
            <span className="small muted">ยังไม่มี — ผูกบัตรสมาชิกเพื่อรับรหัสลูกค้า</span>
          )}
        </div>

        <label className="field">
          <span className="field-lbl">ชื่อ-นามสกุล</span>
          <input value={name} onChange={(e) => setName(e.target.value)} disabled={!editing || nameLocked} maxLength={120} />
          {nameLocked && (
            <span className="small muted">
              ชื่อมาจากบัตรสมาชิก {u.sap_customer_no} — แก้ไขได้ที่สาขาหรือศูนย์บริการลูกค้า
              เพื่อให้ตรงกับใบเสร็จและใบกำกับภาษี
            </span>
          )}
        </label>

        <label className="field">
          <span className="field-lbl">อีเมล</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} disabled={!editing} placeholder="ใช้ส่งใบเสร็จและการแจ้งเตือน" />
        </label>

        <label className="field">
          <span className="field-lbl">เบอร์โทร</span>
          <input value={u.phone || "—"} disabled />
          <span className="small muted">เบอร์นี้ใช้เข้าสู่ระบบ — เปลี่ยนได้ที่สาขาหรือศูนย์บริการลูกค้า</span>
        </label>

        {u.has_password ? (
          <p className="small muted">รหัสผ่าน: ตั้งไว้แล้ว — เปลี่ยนได้ที่เมนู “ลืมรหัสผ่าน” (ยืนยันด้วย OTP)</p>
        ) : (
          <label className="field">
            <span className="field-lbl">ตั้งรหัสผ่าน (ไม่บังคับ)</span>
            <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} disabled={!editing} placeholder="เข้าระบบด้วย OTP ได้อยู่แล้ว" />
          </label>
        )}

        {err && <p className="small err">{err}</p>}
        {msg && !editing && <p className="small ok">{msg}</p>}

        {editing && (
          <div className="row" style={{ gap: 8 }}>
            <button className="btn dark" type="submit" disabled={busy}>{busy ? "กำลังบันทึก…" : "บันทึก"}</button>
            <button className="btn ghost" type="button" onClick={cancel} disabled={busy}>ยกเลิก</button>
          </div>
        )}
      </section>

    </form>
  );
}


function PrivacyPanel() {
  const auth = useAuth();
  const [p, setP] = useState<Privacy | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    apiGet<Privacy>("/me/privacy").then(setP).catch((e) => setErr(errorMessage(e)));
  }, []);

  const toggle = async (marketing: boolean) => {
    setErr(null);
    try {
      setP(await apiPost<Privacy>("/me/consents", { marketing }));
      setMsg(marketing ? "บันทึกความยินยอมแล้ว" : "ถอนความยินยอมแล้ว — ข้อมูลที่เก็บไว้เพื่อการตลาดถูกลบตัวตนย้อนหลัง");
    } catch (e) {
      setErr(errorMessage(e));
    }
  };

  const exportData = async () => {
    setErr(null);
    try {
      const data = await apiGet<unknown>("/me/data/export");
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = "sbdesign-my-data.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(errorMessage(e));
    }
  };

  const deleteMe = async () => {
    setErr(null);
    try {
      await apiPost("/me/data/delete", { confirm: true });
      auth.logout();
    } catch (e) {
      setErr(errorMessage(e));
      setConfirming(false);
    }
  };

  if (!p) return <p className="muted">{err || "กำลังโหลด…"}</p>;
  return (
    <div className="privacy">
      <section className="privacy-box">
        <h2>ความยินยอม</h2>
        <label className="privacy-row">
          <input type="checkbox" checked={p.consent_marketing} onChange={(e) => toggle(e.target.checked)} />
          <span>
            <strong>ให้เก็บพฤติกรรมการใช้งานเพื่อแนะนำสินค้าและการตลาด</strong>
            <span className="small muted d-block">ไม่ยินยอมก็ใช้งานได้ตามปกติ — ระบบยังเก็บข้อมูลเท่าที่จำเป็นต่อการให้บริการ เช่น ตะกร้าและประวัติการสั่งซื้อ</span>
          </span>
        </label>
        {p.consent_marketing_at && <p className="small muted">อัปเดตล่าสุด {new Date(p.consent_marketing_at).toLocaleString("th-TH")}</p>}
        {msg && <p className="small ok">{msg}</p>}
      </section>

      <section className="privacy-box">
        <h2>สิทธิ์ของคุณ</h2>
        <div className="privacy-actions">
          <button className="btn ghost" onClick={exportData}><Icon name="download" size={18} /> ขอสำเนาข้อมูลของฉัน</button>
          {confirming ? (
            <span className="privacy-confirm">
              <span className="small">ลบแล้วกู้คืนไม่ได้ — ยืนยันหรือไม่?</span>
              <button className="btn danger sm" onClick={deleteMe}>ยืนยันลบ</button>
              <button className="btn ghost sm" onClick={() => setConfirming(false)}>ยกเลิก</button>
            </span>
          ) : (
            <button className="btn ghost danger" onClick={() => setConfirming(true)}><Icon name="delete_forever" size={18} /> ขอลบข้อมูลส่วนบุคคล</button>
          )}
        </div>
        <p className="small muted">เอกสารการเงินที่ออกไปแล้ว (ใบเสนอราคา/ใบเสร็จ) ต้องเก็บตามกฎหมาย แต่จะถูกตัดการเชื่อมโยงกับบัญชีของคุณ</p>
      </section>

      {p.history.length > 0 && (
        <section className="privacy-box">
          <h2>ประวัติความยินยอม</h2>
          <ul className="privacy-history">
            {p.history.map((h, i) => (
              <li key={i}><span className={h.granted ? "ok" : "muted"}>{h.granted ? "ยินยอม" : "ถอนความยินยอม"}</span> · {new Date(h.created_at).toLocaleString("th-TH")} · {h.source}</li>
            ))}
          </ul>
        </section>
      )}
      {err && <p className="err">{err}</p>}
    </div>
  );
}

function PendingPanel() {
  const { rows, reload } = usePendingPayments();
  if (rows.length === 0) {
    return <p className="muted">ไม่มีคำสั่งซื้อที่รอชำระเงิน — จ่ายครบแล้วทุกใบ</p>;
  }
  return (
    <div className="pending-list">
      {rows.map((r) => {
        const left = r.seconds_left ?? null;
        const urgent = left !== null && left > 0 && left < 2 * 3600;
        return (
          <div key={r.quotation_no} className={"pending-row" + (urgent ? " urgent" : "")}>
            <div className="pending-main">
              <b className="mono">{r.quotation_no}</b>
              <div className="small muted">
                {r.first_item}{r.item_count > 1 ? ` และอีก ${r.item_count - 1} รายการ` : ""}
              </div>
              <div className={"small " + (urgent ? "red" : "muted")}>
                <Icon name="schedule" size={13} /> {timeLeftText(left)}
                {left !== null && left > 0 && " · ไม่ชำระภายในเวลาจะถูกยกเลิกอัตโนมัติ"}
              </div>
            </div>
            <div className="pending-side">
              <b>{baht(r.amount)}</b>
              <Link to={`/pay/${r.quotation_no}`} className="btn primary sm" onClick={reload}>ชำระเงิน</Link>
              <Link to={`/q/${r.quotation_no}`} className="link-btn small">ดูรายละเอียด</Link>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function AccountPage() {
  const wishStore = useWishlist(true);  // ตัวเก็บสถานะร่วมกับปุ่มหัวใจบนการ์ด
  const { tab: raw } = useParams();
  const tab = (TABS.find((t) => t.key === raw)?.key || "orders") as (typeof TABS)[number]["key"];
  const auth = useAuth();
  const [orders, setOrders] = useState<OrderHistory[] | null>(null);
  const [wish, setWish] = useState<MaterialCard[] | null>(null);
  const [recent, setRecent] = useState<MaterialCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    if (tab === "recent") {
      apiGet<MaterialCard[]>("/me/recently-viewed?limit=24").then(setRecent).catch((e) => setError(errorMessage(e)));
      return;
    }
    if (!auth.user) return;
    if (tab === "orders") apiGet<OrderHistory[]>("/me/orders").then(setOrders).catch((e) => setError(errorMessage(e)));
    if (tab === "wishlist") apiGet<MaterialCard[]>("/me/wishlist").then(setWish).catch((e) => setError(errorMessage(e)));
  }, [tab, auth.user]);

  // ใช้ตัวเก็บสถานะร่วมกับปุ่มหัวใจบนการ์ด ไม่ยิง API เอง —
  // ของเดิมยิงตรงทำให้ตัวเก็บสถานะไม่รู้เรื่อง หัวใจบนการ์ดในหน้านี้เลยเป็นสีเข้มทั้งที่อยู่ในรายการโปรด
  const unwish = async (matnr: string) => {
    await wishStore.toggle(matnr);
    setWish((cur) => (cur || []).filter((m) => m.matnr !== matnr));
  };

  return (
    <main className="container sec account">
      <h1>บัญชีของฉัน</h1>
      <nav className="account-tabs">
        {TABS.map((t) => (
          <Link key={t.key} to={`/account/${t.key}`} className={"account-tab" + (tab === t.key ? " on" : "")}>
            <Icon name={t.icon} size={18} /> {t.label}
          </Link>
        ))}
      </nav>

      {/* ผูกเลขสมาชิกทีหลังได้ — คนที่ข้ามตอนเข้าสู่ระบบ หรือเพิ่งไปสมัครที่สาขามา
          ผูกแล้วไม่ต้องโชว์อีก ไม่งั้นทุกแท็บจะมีกล่องชวนผูก/ชวนกรอกโปรไฟล์ค้างอยู่ตลอด */}
      {auth.user?.role === "customer" && !auth.user.sap_customer_no && <MemberLink compact />}

      {error && <p className="err">{error}</p>}
      {!auth.user && tab !== "recent" && <p className="muted">เข้าสู่ระบบเพื่อดู{TABS.find((t) => t.key === tab)?.label}ของคุณ</p>}

      {tab === "pending" && <PendingPanel />}
      {tab === "profile" && <ProfilePanel />}
      {tab === "addresses" && auth.user && <AddressPanel />}
      {tab === "orders" && auth.user && (
        orders === null ? <p className="muted">กำลังโหลด…</p>
          : orders.length === 0 ? <p className="muted">ยังไม่มีประวัติการสั่งซื้อ</p>
            : <div className="order-list">{orders.map((o) => <OrderRow key={o.so_no} o={o} />)}</div>
      )}

      {tab === "wishlist" && auth.user && (
        wish === null ? <p className="muted">กำลังโหลด…</p>
          : wish.length === 0 ? <p className="muted">ยังไม่มีรายการโปรด — กดรูปหัวใจที่หน้าสินค้าเพื่อเก็บไว้</p>
            : <div className="pgrid">{wish.map((m) => (
              <ProductCard key={m.matnr} item={m} action={<button className="btn ghost sm" onClick={() => unwish(m.matnr)}>เอาออกจากรายการโปรด</button>} />
            ))}</div>
      )}

      {tab === "privacy" && auth.user && <PrivacyPanel />}

      {tab === "recent" && (
        recent === null ? <p className="muted">กำลังโหลด…</p>
          : recent.length === 0 ? <p className="muted">ยังไม่ได้ดูสินค้าไหนเลย</p>
            : <div className="pgrid">{recent.map((m) => <ProductCard key={m.matnr} item={m} />)}</div>
      )}
    </main>
  );
}
