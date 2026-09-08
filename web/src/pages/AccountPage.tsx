import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Icon from "../components/Icon";
import ProductCard from "../components/ProductCard";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { baht } from "../lib/format";
import type { MaterialCard, OrderHistory } from "../lib/types";

const TABS = [
  { key: "orders", label: "ประวัติการสั่งซื้อ", icon: "receipt_long" },
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

export default function AccountPage() {
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

  const unwish = async (matnr: string) => {
    await apiPost(`/me/wishlist/${matnr}`);
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

      {error && <p className="err">{error}</p>}
      {!auth.user && tab !== "recent" && <p className="muted">เข้าสู่ระบบเพื่อดู{TABS.find((t) => t.key === tab)?.label}ของคุณ</p>}

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
