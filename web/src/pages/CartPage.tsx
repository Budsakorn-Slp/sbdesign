import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Icon from "../components/Icon";
import Placeholder from "../components/Placeholder";
import { imageSources } from "../lib/images";
import { ApiError, api, apiGet, apiPost, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { shipNeedsReview, useCart } from "../lib/cart";
import { useContent } from "../lib/content";
import { bahtWord, thTime } from "../lib/format";
import { useCartSocket } from "../lib/realtime";
import type { CartItem } from "../lib/types";

const LOGIN_NOTE_MS = 60_000;          // 1 นาที
const LOGIN_NOTE_KEY = "sb_login_note";  // ต่อหนึ่งแท็บ/หนึ่งการเข้าใช้งาน

export default function CartPage() {
  const auth = useAuth();
  const { cart, loading, error, update, remove, select, setShipTo, refresh, setCart } = useCart();
  const { plants, shipTo } = useContent();
  const nav = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  // จอเล็ก: สรุปคำสั่งซื้อเป็นแผงลอยจากขอบล่าง (แบบเดียวกับฝั่งพนักงาน)
  // ของเดิมต้องเลื่อนผ่านสินค้าทั้งตะกร้าลงไปสุดหน้าถึงจะเห็นยอดรวมกับปุ่มชำระเงิน
  const [sheet, setSheet] = useState(false);
  // ป้าย "เข้าสู่ระบบแล้ว" เป็นคำยืนยันชั่วคราว ไม่ใช่สถานะถาวร — โชว์ครั้งเดียวต่อการเข้าใช้งาน
  // แล้วหายไปเองใน 1 นาที (ต่างจากป้าย "ยังไม่ได้เข้าสู่ระบบ" ที่ต้องค้างไว้ เพราะเป็นสิ่งที่ยังต้องทำ)
  const [loginNote, setLoginNote] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [live, setLive] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [codeErr, setCodeErr] = useState<string | null>(null);
  // ข้อความบอกสถานะที่ไม่ใช่ความผิดพลาด เช่น ใส่โค้ดเดิมซ้ำ
  const [codeNote, setCodeNote] = useState<string | null>(null);
  // โค้ดที่ใช้ร่วมกับของเดิมไม่ได้ — ไม่ตีกลับเฉยๆ แต่ให้ลูกค้าเลือกเองว่าจะเอาอันไหน
  const [conflict, setConflict] = useState<{ code: string; message: string; amount: number } | null>(null);

  // realtime: เซลล์เพิ่ม/แก้ของ → รีเฟรชทันที + เด้งข้อความ
  useCartSocket(cart?.id, (evt) => {
    if (evt.type === "hello") return;
    refresh();
    if (evt.type === "item_added" && evt.added_by === "sales") setLive(`${evt.by_name || "พนักงานขาย"} เพิ่มสินค้าให้คุณ 1 รายการ — ตรวจสอบด้านล่าง`);
    else if (evt.type === "customer_attached") setLive(`${evt.sales_name || "พนักงานขาย"} เริ่มช่วยดูแลตะกร้าของคุณ`);
    else if (evt.type === "session_closed") setLive("พนักงานขายจบการดูแลตะกร้านี้แล้ว — ตะกร้ายังเป็นของคุณ");
  });
  useEffect(() => {
    if (!live) return;
    const t = setTimeout(() => setLive(null), 6000);
    return () => clearTimeout(t);
  }, [live]);

  // ค่าส่งจริงคิดจากปลายทาง — ส่งรหัสไปรษณีย์ที่เลือกไว้บน nav (หรือที่อยู่หลักของสมาชิก) ให้หลังบ้าน
  const wantPostcode = shipTo?.postcode || auth.user?.default_postcode || null;
  const sentPostcode = useRef<string | null>(null);
  useEffect(() => {
    if (!cart || !wantPostcode) return;
    if (cart.delivery?.postcode === wantPostcode || sentPostcode.current === wantPostcode) return;
    sentPostcode.current = wantPostcode; // จำไว้กันยิงซ้ำถ้าหลังบ้านไม่รับรหัสนี้
    setShipTo(wantPostcode).catch(() => {});
  }, [cart, wantPostcode, setShipTo]);

  const plantName = (code: string | null) => plants.find((p) => p.plant_code === code)?.name || code || "";
  // ค่าบริการขนส่งที่พนักงานเปิดไว้ ไม่ใช่ "สินค้า" ที่ลูกค้าเลือก
  // ฝั่งพนักงานต้องเห็นเลข MATNR ไว้คุยกับคลัง/SAP แต่ลูกค้าเห็นแล้วสับสนว่าซื้ออะไรไป
  // ยอดไปแสดงแยกบรรทัดในกล่องสรุปคำสั่งซื้อแทน
  // ธง is_charge มาจากไฟล์กฎฝั่งหลังบ้าน — เติมรหัสค่าบริการใหม่แล้วหน้านี้รู้เอง
  const shipLines = (cart?.items || []).filter((it) => it.is_charge && it.selected);
  const items = (cart?.items || []).filter((it) => !it.is_charge);
  const canPay = auth.role === "customer";
  // ของตัวโชว์/ฝากขาย (MATNR ขึ้นต้น 20 / 25) — ใส่ตะกร้าได้ แต่ยังจ่ายออนไลน์ไม่ได้
  // ต้องไปดูของจริงแล้วรับที่สาขา · วันที่เปิดขายออนไลน์ได้ หลังบ้านปลดล็อกแล้วธงนี้จะเป็น false เอง
  const pickupOnly = items.filter((it) => it.selected && it.pickup_only);

  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    setMsg(null);
    try {
      await fn();
    } catch (e) {
      setMsg(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  /** ออกจากการดูแลของพนักงาน กลับไปสั่งออนไลน์เอง
   *  เตือนก่อนเพราะส่วนลดหน้าร้านถูกถอดทั้งหมด และกดแล้วย้อนเองไม่ได้ ต้องให้พนักงานผูกใหม่ */
  const leaveSalesCare = () => {
    const n = cart?.totals?.lines.length || 0;
    const warn = n ? `ส่วนลด ${n} รายการที่พนักงานใส่ให้จะถูกยกเลิกทั้งหมด

` : "";
    if (!confirm(`${warn}ออกจากการดูแลของพนักงาน แล้วสั่งซื้อออนไลน์เอง?
สินค้าในตะกร้ายังอยู่ครบ`)) return;
    return run("leave", async () => {
      setCart(await api<Cart>("DELETE", `/cart/${cart!.id}/sales-owner`));
      setLive("ออกจากการดูแลของพนักงานแล้ว — สั่งซื้อออนไลน์ได้เลย");
    });
  };

  /** ถอดโค้ดออก เพื่อเปลี่ยนไปใช้โค้ดอื่น */
  const removeDiscount = (id: string) =>
    run(id, async () => {
      setCodeErr(null);
      try {
        setCart(await api<Cart>("DELETE", `/cart/${cart!.id}/discounts/${id}`));
      } catch (e) {
        setCodeErr(errorMessage(e));
      }
    });

  /** ใส่โค้ดส่วนลดจากกล่องสรุป — ใช้ได้เฉพาะตะกร้าที่ไม่มีพนักงานดูแล */
  const applyCode = (e: React.FormEvent) => {
    e.preventDefault();
    const c = code.trim().toUpperCase();
    if (!c || !cart) return;
    setCodeErr(null);
    setCodeNote(null);
    setConflict(null);
    // ใส่โค้ดเดิมซ้ำ ฝั่งเซิร์ฟเวอร์คืนอันเดิมกลับมาเฉยๆ (ถูกแล้ว กดซ้ำไม่ควรลดสองเด้ง)
    // แต่ถ้าไม่บอกอะไรเลย หน้าจอจะแค่ล้างช่องที่พิมพ์ไป เหมือนกดแล้วโค้ดหายไปดื้อๆ
    const already = cart.totals?.lines.some((l) => l.kind === "promotion" && l.code === c);
    if (already) {
      setCode("");
      setCodeNote(`ใช้ ${c} อยู่แล้ว — ดูบรรทัดส่วนลดด้านบน`);
      return;
    }
    return run("code", async () => {
      try {
        setCart(await apiPost<Cart>(`/cart/${cart.id}/discounts`, { kind: "promotion", promo_code: c }));
        setCode("");
      } catch (e2) {
        // 409 = ใช้ร่วมกับโค้ดที่ใส่ไว้แล้วไม่ได้ ไม่ใช่โค้ดผิด — ถามลูกค้าว่าจะเอาอันไหน
        if (e2 instanceof ApiError && e2.status === 409) {
          // หลังบ้านแนบมูลค่าของโค้ดใหม่มาใน detail ด้วย ลูกค้าจะได้เทียบก่อนตัดสินใจสลับ
          const d = (e2.detail && typeof e2.detail === "object" ? e2.detail : {}) as { amount?: string };
          setConflict({ code: c, message: errorMessage(e2), amount: Number(d.amount ?? 0) });
        }
        else setCodeErr(errorMessage(e2));
      }
    });
  };

  /** ถอดโค้ดเดิมทั้งหมดแล้วใช้โค้ดใหม่แทน — ทางเลือกตอนใช้ร่วมกันไม่ได้ */
  const swapToNewCode = () => {
    if (!cart || !conflict) return;
    const target = conflict.code;
    return run("code", async () => {
      try {
        let latest = cart;
        for (const l of cart.totals?.lines.filter((x) => x.kind === "promotion") ?? []) {
          latest = await api<Cart>("DELETE", `/cart/${cart.id}/discounts/${l.id}`);
        }
        setCart(await apiPost<Cart>(`/cart/${cart.id}/discounts`, { kind: "promotion", promo_code: target }));
        void latest;
        setCode("");
        setConflict(null);
      } catch (e) {
        setConflict(null);
        setCodeErr(errorMessage(e));
      }
    });
  };

  // ติ๊ก = เก็บที่ฝั่งเซิร์ฟเวอร์ (cart_items.selected) เพราะยอดรวม ส่วนลด ค่าส่ง และการชำระเงินคิดจากรายการที่ติ๊กเท่านั้น
  const picked = items.filter((it) => it.selected).map((it) => it.id);
  const allPicked = items.length > 0 && picked.length === items.length;
  const togglePick = (it: CartItem) => run(it.id, () => select([it.id], !it.selected));
  const toggleAll = () => run("bulk", () => select(null, !allPicked));
  const removePicked = () =>
    run("bulk", async () => {
      for (const id of picked) await remove(id);
    });

  const checkout = () =>
    run("checkout", async () => {
      await apiPost("/cart/checkout-check");
      nav("/checkout");
    });

  /** เอาของที่รับได้เฉพาะที่สาขาออกจากรายการที่ติ๊ก — ของยังอยู่ในตะกร้า แค่ไม่คิดเงินรอบนี้ */
  const unpickBranchOnly = () =>
    run("unpick", () => select(pickupOnly.map((it) => it.id), false));

  const t = cart?.totals;
  const shipPostcode = cart?.delivery?.postcode || null;
  const shipFee = Number(t?.shipping_fee || 0);
  const shipDiscount = Number(t?.shipping_discount || 0);
  const needsShip = items.some((it) => it.selected && (it.supply_mode === "ship" || it.supply_mode === "install"));
  const shipReview = shipNeedsReview(t?.warnings);

  useEffect(() => {
    if (!auth.user) return;
    try {
      if (sessionStorage.getItem(LOGIN_NOTE_KEY)) return;  // รอบนี้เคยเห็นแล้ว ไม่ต้องโชว์ซ้ำทุกครั้งที่เปิดตะกร้า
    } catch {
      /* โหมดไม่ระบุตัวตน/ปิดคุกกี้ — โชว์แล้วหายเองก็ยังทำงานถูก */
    }
    setLoginNote(true);
    const t = setTimeout(() => {
      setLoginNote(false);
      try {
        sessionStorage.setItem(LOGIN_NOTE_KEY, "1");
      } catch {
        /* เก็บไม่ได้ก็ไม่เป็นไร */
      }
    }, LOGIN_NOTE_MS);
    return () => clearTimeout(t);
  }, [auth.user]);

  // ทางแยกสำหรับพนักงาน ต้องอยู่ "หลัง" hook ทุกตัว
  // เดิมวางไว้กลางฟังก์ชัน พอ auth โหลดเสร็จแล้ว role เปลี่ยนจาก undefined เป็น sales
  // React จะเจอว่ารอบนี้เรียก hook น้อยกว่ารอบก่อน แล้วโยน "Rendered fewer hooks than expected"
  // หน้าตะกร้าขาวทั้งหน้าเมื่อเปิดด้วยบัญชีพนักงาน
  if (auth.role === "sales" || auth.role === "manager") {
    return (
      <main className="container sec">
        <div className="card">
          <b>โหมดพนักงานขาย</b> — ตะกร้าของลูกค้าจัดการที่หน้า <Link to="/sales" className="strong">ตะกร้าที่กำลังดูแล</Link> (STEP 4)
        </div>
      </main>
    );
  }

  return (
    <main className="container sec cart">
      <Link to="/search" className="row small muted" style={{ marginBottom: 10 }}><Icon name="arrow_back" size={18} /> กลับไปช้อปต่อ</Link>
      <h1 className="cart-title">ตะกร้าสินค้าของคุณ</h1>

      <div className="cart-grid has-sheet">
        <div className="cart-main">
          {auth.role === "guest" && (
            <div className="banner guest">
              <Icon name="lock" size={22} />
              <div className="grow">
                คุณยังไม่ได้เข้าสู่ระบบ — เพิ่ม/ลบสินค้าในตะกร้าได้ แต่ต้องเข้าสู่ระบบก่อนชำระเงิน หรือให้พนักงานขายช่วยดูแลตะกร้านี้
                <div style={{ marginTop: 8 }}><button className="btn dark sm" onClick={auth.openLogin}>เข้าสู่ระบบ</button></div>
              </div>
            </div>
          )}
          {auth.role === "customer" && auth.user && loginNote && (
            <div className="banner ok">
              <Icon name="verified_user" size={22} />
              <div className="grow">เข้าสู่ระบบแล้ว — สะสมพ้อยท์และชำระเงินได้ทันที</div>
            </div>
          )}
          {cart?.owner_sales && (
            <div className="banner sales">
              <Icon name="support_agent" size={22} />
              <div className="grow">
                <b>{cart.owner_sales.name}</b> กำลังช่วยดูแลตะกร้านี้ · สาขา{plantName(cart.owner_sales.branch_id)} · SESSION {cart.no}
                <div className="tiny">ระหว่างนี้ชำระเงินออนไลน์เองไม่ได้ ส่วนลดให้พนักงานเป็นคนใส่ให้</div>
              </div>
              {/* ทางออกให้ลูกค้าที่เปลี่ยนใจอยากสั่งออนไลน์เอง — ต้องเตือนเรื่องส่วนลดก่อน
                  เพราะสิทธิ์หน้าร้านจะถูกถอดทั้งหมด กดแล้วย้อนเองไม่ได้ ต้องให้พนักงานผูกใหม่ */}
              <button className="btn sm" disabled={!!busy} onClick={leaveSalesCare}>ออกจากการดูแล</button>
            </div>
          )}

          {msg && <div className="note err" style={{ marginBottom: 12 }}>{msg}</div>}
          {error && <div className="note err" style={{ marginBottom: 12 }}>{error}</div>}

          {!cart && loading && <div className="ph" style={{ height: 200 }}>กำลังโหลดตะกร้า…</div>}

          {cart && items.length === 0 && (
            <div className="cart-empty">
              <Icon name="shopping_cart" size={48} />
              <div className="strong">ยังไม่มีสินค้าในตะกร้า</div>
              <Link to="/search" className="btn dark">เลือกซื้อสินค้า</Link>
            </div>
          )}

          {cart && items.length > 0 && (
            <>
              <p className="cart-intro">สินค้ากำลังรอคุณอยู่ในตะกร้าทั้งหมด {cart.all_count} ชิ้น ชำระเงินง่าย ๆ อีกเพียงไม่กี่ขั้นตอน เลือกใช้บริการจัดส่งแล้วรอรับสินค้าที่บ้านได้เลย!</p>
              <div className="cart-bulk">
                <label className="row small">
                  <input type="checkbox" className="cart-pick" checked={allPicked} disabled={busy === "bulk"} onChange={toggleAll} aria-label="เลือกทั้งหมด" />
                  เลือกทั้งหมด{picked.length > 0 ? ` (เลือกแล้ว ${picked.length} รายการ)` : ""}
                </label>
                <button className="link-btn" disabled={!picked.length || busy === "bulk"} onClick={removePicked}>
                  <Icon name="delete" size={16} /> ลบที่เลือก
                </button>
              </div>
              <div className="cart-items">
                {items.map((it) => (
                  <CartRow key={it.id} it={it} busy={busy === it.id || busy === "bulk"} picked={it.selected} onPick={() => togglePick(it)}
                    onInc={() => run(it.id, () => update(it.id, { qty: it.qty + 1 }))}
                    onDec={() => it.qty > 1 && run(it.id, () => update(it.id, { qty: it.qty - 1 }))}
                    onRemove={() => run(it.id, () => remove(it.id))} />
                ))}
              </div>
              {/* ช่องล่างสุด: ยอดรวมของรายการที่ติ๊กไว้ทั้งหมด */}
              <div className="cart-foot">
                <span>ยอดรวมสินค้าที่เลือก ({cart.count} ชิ้น)</span>
                <b>{bahtWord(cart.subtotal)}</b>
              </div>
            </>
          )}
        </div>

        <aside className={"cart-side sheet" + (sheet ? " on" : "")}>
          {/* แถบลอย: ปิดอยู่เห็นยอดรวม + ปุ่มชำระเงิน · แตะเพื่อกางดูสรุปเต็ม (จอใหญ่ CSS ซ่อนแถบนี้) */}
          <div className="sum-bar">
            <button className="sum-bar-open" onClick={() => setSheet((v) => !v)} aria-expanded={sheet} aria-controls="cart-summary">
              <span>
                <small>{sheet ? "แตะเพื่อย่อสรุป" : `ยอดรวม · ${cart?.count || 0} ชิ้น`}</small>
                <b>{bahtWord(t?.grand_total ?? t?.net_total ?? cart?.subtotal ?? 0)}</b>
              </span>
              <Icon name={sheet ? "expand_more" : "expand_less"} size={20} />
            </button>
            {canPay ? (
              <button className="btn primary sum-bar-cta" disabled={!cart?.selected_count || busy === "checkout" || pickupOnly.length > 0}
                      title={pickupOnly.length ? "มีสินค้าที่ต้องรับที่สาขา" : ""} onClick={checkout}>
                ชำระเงิน{cart?.selected_count ? ` (${cart.selected_count})` : ""}
              </button>
            ) : (
              <button className="btn dark sum-bar-cta" onClick={auth.openLogin}>เข้าสู่ระบบ</button>
            )}
          </div>
          <div className="summary" id="cart-summary">
            <h3>สรุปคำสั่งซื้อ</h3>
            <div className="sum-row"><span>สินค้า ({cart?.count || 0})</span><b>{bahtWord(cart?.subtotal || 0)}</b></div>
            {/* ส่วนลดที่เหลือ 0 ไม่ต้องโชว์ "−0 บาท" */}
            {cart?.totals?.lines.filter((l) => Number(l.amount) > 0).map((l) => (
              <div key={l.id} className="sum-row">
                <span>
                  {l.title}{l.status === "pending_approval" ? " (รออนุมัติ)" : ""}
                  {/* ถอดโค้ดออกได้เฉพาะตอนไม่มีพนักงานดูแล — ส่วนลดที่พนักงานใส่ให้ ลูกค้าแตะเองไม่ได้
                      (ปุ่มนี้คือทางเดียวที่จะเปลี่ยนไปใช้โค้ดอื่น เพราะใส่ซ้อนกันไม่ได้) */}
                  {!cart?.owner_sales && (
                    <button className="link-btn small danger" style={{ marginLeft: 8 }}
                            disabled={busy === l.id} onClick={() => removeDiscount(l.id)}>
                      เอาออก
                    </button>
                  )}
                </span>
                <span className={l.status === "applied" ? "green" : "muted"}>−{bahtWord(l.amount)}</span>
              </div>
            ))}
            {/* ช่องใส่โค้ดอยู่ในกล่องสรุปเลย ไม่ต้องกดเปิดหน้าต่างก่อน
                — ลูกค้าที่ถือโค้ดมาอยากใส่ทันที การซ่อนไว้หลังปุ่มคือขั้นตอนที่ไม่ได้ช่วยอะไร

                ตะกร้าที่พนักงานดูแลอยู่ไม่มีช่องนี้ ส่วนลดเป็นหน้าที่ของพนักงาน
                (ฝั่งหลังบ้านก็กันไว้อีกชั้น ลูกค้ายิง API เองก็ไม่ผ่าน) */}
            {cart?.owner_sales ? (
              !!cart.totals?.lines.length && (
                <div className="sum-row small muted"><span>ส่วนลดจากพนักงานที่ดูแล</span><span /></div>
              )
            ) : (
              <form className="promo-code-row" onSubmit={applyCode}>
                <Icon name="local_offer" size={16} />
                <input
                  value={code}
                  onChange={(e) => { setCode(e.target.value.toUpperCase()); setCodeErr(null); setCodeNote(null); }}
                  placeholder="มีโค้ดส่วนลด? ใส่ที่นี่"
                  autoComplete="off"
                  disabled={!items.length}
                />
                <button className="btn sm" type="submit" disabled={!code.trim() || !items.length || busy === "code"}>
                  {busy === "code" ? "กำลังใช้…" : "ใช้โค้ด"}
                </button>
              </form>
            )}
            {codeErr && <div className="note err tiny" style={{ marginBottom: 8 }}>{codeErr}</div>}
            {codeNote && <div className="note tiny" style={{ marginBottom: 8 }}>{codeNote}</div>}
            {conflict && (
              <div className="note warn tiny code-conflict">
                {/* สองบรรทัดพอ: ใช้ร่วมไม่ได้ + ตัวใหม่ลดเท่าไร
                    ข้อความเต็มจากหลังบ้านมีหางบอกวิธีแก้ ("— เอา X ออกก่อน") ซึ่งซ้ำกับปุ่มข้างล่าง */}
                <div>{conflict.message.split(" — ")[0]}</div>
                <div>{conflict.code} ลด {bahtWord(conflict.amount)}</div>
                <div className="row" style={{ gap: 8, marginTop: 6 }}>
                  <button className="btn sm" disabled={busy === "code"} onClick={swapToNewCode}>
                    ใช้ {conflict.code} แทน
                  </button>
                  <button className="link-btn small" onClick={() => { setConflict(null); setCode(""); }}>
                    ใช้โค้ดเดิมต่อ
                  </button>
                </div>
              </div>
            )}
            {/* ค่าขนส่งที่พนักงานเปิดเป็น Mat ไว้ — แจกแจงให้ลูกค้าเห็นว่าแต่ละก้อนคืออะไร
                (ตัวบรรทัดจริงถูกซ่อนจากลิสต์สินค้าไปแล้ว ไม่งั้นดูเหมือนซื้อของเพิ่ม) */}
            {shipLines.map((it) => (
              <div key={it.id} className="sum-row small muted">
                <span>· {it.name}</span><span>{bahtWord(it.line_total)}</span>
              </div>
            ))}
            {/* ค่าส่งจริงตามเขตของปลายทาง — ยังไม่เลือกจังหวัดก็ยังคิดไม่ได้ อย่าโชว์เลขมั่ว */}
            <div className="sum-row">
              <span>
                รวมค่าจัดส่ง
              </span>
              {!needsShip ? (
                <span className="muted">ไม่มีรายการที่ต้องจัดส่ง</span>
              ) : !shipPostcode ? (
                <span className="muted">เลือกจังหวัดจัดส่งด้านบนเพื่อดูค่าส่ง</span>
              ) : shipReview ? (
                <span className="muted">รอเจ้าหน้าที่ประเมิน</span>
              ) : shipFee > 0 ? (
                <b>{bahtWord(t?.shipping_fee || 0)}</b>
              ) : (
                <span className="green">จัดส่งฟรี</span>
              )}
            </div>
            {shipDiscount > 0 && (
              <div className="sum-row"><span>ส่วนลดค่าจัดส่ง</span><span className="green">−{bahtWord(t?.shipping_discount || 0)}</span></div>
            )}
            {Number(t?.install_fee || 0) > 0 && (
              <div className="sum-row"><span>ค่าติดตั้ง</span><b>{bahtWord(t?.install_fee || 0)}</b></div>
            )}
            <div className="sum-row"><span className="muted"><i>หรือ</i> <u>ใช้บริการรับที่สาขา</u></span><span className="muted">ไม่มีค่าบริการ</span></div>
            <div className="sum-total">
              <span>ยอดรวม<small>{!needsShip || (shipPostcode && !shipReview) ? "รวมค่าจัดส่งแล้ว · ไม่รวมค่าประกอบสินค้า" : "ยังไม่รวมค่าจัดส่ง"}</small></span>
              <b>{bahtWord(t?.grand_total ?? t?.net_total ?? cart?.subtotal ?? 0)}</b>
            </div>
            <p className="tiny muted">เมื่อคลิก "ชำระเงิน" แสดงว่าคุณยอมรับ <u>นโยบายความเป็นส่วนตัว</u></p>
            {/* มีของที่ต้องรับที่สาขาอยู่ในรายการที่ติ๊ก — บอกเหตุผลและทางออกก่อนปุ่ม
                ไม่ใช่ปล่อยให้กดแล้วเด้ง error (หลังบ้านก็กันอีกชั้นอยู่ดี) */}
            {pickupOnly.length > 0 && (
              <div className="note warn small" style={{ marginTop: 10 }}>
                <b>{pickupOnly.length} รายการต้องรับที่สาขา</b> — ของตัวโชว์และของฝากขายมีชิ้นเดียวต่อสาขา
                ยังสั่งซื้อออนไลน์ไม่ได้ ดูสาขาที่มีของได้ที่รายการสินค้าด้านบน
                <button className="link-btn small" style={{ marginLeft: 6 }} disabled={busy === "unpick"} onClick={unpickBranchOnly}>
                  เอาออกจากรายการที่เลือก
                </button>
              </div>
            )}
            {canPay ? (
              <button className="btn primary lg block" disabled={!cart?.selected_count || busy === "checkout" || pickupOnly.length > 0}
                      title={pickupOnly.length ? "มีสินค้าที่ต้องรับที่สาขา" : ""} onClick={checkout}>
                ชำระเงิน{cart?.selected_count ? ` (${cart.selected_count} รายการ)` : ""}
              </button>
            ) : (
              <button className="btn dark lg block" onClick={auth.openLogin}><Icon name="lock" size={18} /> เข้าสู่ระบบเพื่อชำระเงิน</button>
            )}
            <div className="pay-icons">
              {["VISA", "MC", "PromptPay", "TrueMoney", "LINE Pay", "ผ่อน 0%"].map((p) => (
                <span key={p} className="ftr-pay mono">{p}</span>
              ))}
            </div>
            <div className="row small" style={{ marginTop: 12 }}><Icon name="volunteer_activism" size={18} /> <u>365 วันในการเปลี่ยนความคิดของคุณ</u></div>
          </div>

        </aside>

        {/* นอกแผงสรุป — บนจอเล็ก aside กลายเป็นแผงลอยติดขอบล่าง ของพวกนี้อยู่ข้างในไม่ได้
            (toast ลอยเองอยู่แล้ว · แผงโปรฯ เป็น modal)
            การ์ด "สิทธิ์ของบัญชี" ตัดออก — เป็นภาษาของระบบ ลูกค้าไม่ได้เข้ามาที่ตะกร้าเพื่ออ่านว่า
            ตัวเองทำอะไรได้บ้าง และบรรทัด "ไม่เห็นต้นทุน/สต็อกข้ามสาขา" ยิ่งไม่ควรโผล่ฝั่งลูกค้า */}
        {live && <div className="toast" role="status"><Icon name="notifications_active" size={20} /> {live}</div>}
        {/* กางแผงอยู่แล้วแตะนอกแผง = ย่อกลับ (จอใหญ่ CSS ซ่อนฉากหลังนี้) */}
        {sheet && <div className="scrim" onClick={() => setSheet(false)} />}
      </div>
    </main>
  );
}

/** ป้ายสต็อกในตะกร้า — ใช้เกณฑ์เดียวกับการ์ดสินค้า ลูกค้าจะได้ไม่เห็นคำต่างกันสองที่
 *  ตัวเลขมาจาก cache (อายุไม่เกิน TTL) ไม่ใช่ยอดสด — ของจริงยืนยันอีกทีตอนสั่งซื้อ
 *  รหัสที่ยังไม่เคยเช็คกับ SAP จะไม่ขึ้นป้ายเลย ดีกว่าโชว์ "มีสต็อก 0 ชิ้น" ซึ่งไม่จริง
 */
function StockTag({ it }: { it: CartItem }) {
  if (!it.stock) return null;
  const ready = it.stock.ready_qty || 0;
  const later = it.stock.later_qty || 0;
  const made = !!it.stock.made_to_order;
  if (ready >= it.qty) {
    return <div className={"cart-stock" + (ready <= 5 ? " low" : " ok")}>{ready <= 5 ? `เหลือ ${ready} ชิ้น` : `มีสต็อก ${ready} ชิ้น`}</div>;
  }
  // ของไม่พอกับจำนวนที่สั่ง — บอกตรงๆ ตั้งแต่ในตะกร้า ไม่ใช่ให้ไปเจอตอนกดจ่ายเงิน
  if (ready > 0) return <div className="cart-stock low">มีของ {ready} ชิ้น · ที่เหลือรอของเข้า</div>;
  if (later > 0 || made) return <div className="cart-stock pre">พรีออเดอร์ — สั่งได้ ใช้เวลารอของ</div>;
  return <div className="cart-stock no">สินค้าหมด</div>;
}

/** "มีที่สาขาไหนบ้าง" สำหรับของตัวโชว์/ฝากขาย — กดแล้วค่อยยิงถาม ไม่ถามล่วงหน้าทุกใบ
 *  (เช็คสต็อกรายสาขาเป็นการยิง SAP สด ถ้าถามทุกใบตอนเปิดตะกร้าจะช้าและเปลืองโควตา) */
function BranchPicker({ it }: { it: CartItem }) {
  // รายชื่อสาขามากับตะกร้าอยู่แล้ว (ฟิลด์ NAME ของ STOCK_ON_SITES ฝั่ง SAP) ไม่ต้องกดโหลด
  // ของเดิมให้กด "ดูสาขาที่มีของ" แล้วไปยิง /materials/{id}/stock ซึ่งอ่านสาขาจำลอง 4 แห่ง
  // ของเรา ไม่ใช่โชว์รูมจริง 32 แห่ง — ลูกค้าได้คำตอบที่ไม่ตรงกับที่ไปเจอหน้าร้าน
  const sites = it.show_at_sites || [];
  return (
    <div className="pickup-box">
      <div className="pickup-head"><Icon name="storefront" size={15} /> รับที่สาขาเท่านั้น · ยังสั่งซื้อออนไลน์ไม่ได้</div>
      {/* เงื่อนไขต้องอยู่ตรงที่ลูกค้าตัดสินใจ ไม่ใช่ซ่อนอยู่ในหน้านโยบาย */}
      <div className="pickup-head warn"><Icon name="block" size={15} /> ซื้อแล้วไม่รับเปลี่ยนหรือคืน</div>
      {sites.length === 0 ? (
        /* บอกเท่าที่รู้จริง ดีกว่าโชว์รายชื่อสาขาแบบเดา ซึ่งทำให้ลูกค้าขับรถไปเก้อ */
        <div className="tiny muted">
          {it.stock?.ready_qty ? `มีของรวมทุกสาขา ${it.stock.ready_qty} ชิ้น · ` : ""}
          ยังไม่มีข้อมูลว่าตั้งอยู่สาขาไหน — โทรถามสาขาที่สะดวกก่อนเดินทาง
        </div>
      ) : (
        <>
          <div className="pickup-head ok"><Icon name="visibility" size={15} /> ไปดูของจริงได้ที่ {sites.length} สาขา</div>
          <ul className="pickup-list">
            {sites.map((r) => (
              <li key={r.plant_code}><b>{r.name}</b>{r.qty > 1 ? ` · มี ${r.qty} ชิ้น` : ""}</li>
            ))}
          </ul>
          <div className="tiny muted">ยอดอัปเดตเป็นรอบ — โทรเช็คกับสาขาก่อนเดินทาง</div>
        </>
      )}
    </div>
  );
}

function CartRow({ it, busy, picked, onPick, onInc, onDec, onRemove }: { it: CartItem; busy: boolean; picked: boolean; onPick: () => void; onInc: () => void; onDec: () => void; onRemove: () => void }) {
  return (
    <div className={"cart-row" + (picked ? " picked" : "")}>
      {/* หัวแถว: ติ๊กเลือก · รูป · ชื่อ+รหัส · ปุ่มแก้ไข/ลบ */}
      <div className="cart-row-head">
        <input type="checkbox" className="cart-pick" checked={picked} disabled={busy} onChange={onPick} aria-label={`เลือก ${it.name}`} />
        <Link to={`/p/${it.matnr}`} className="cart-img"><Placeholder src={imageSources(it.matnr, it.image_url)} label="1:1" /></Link>
        <div className="cart-info">
          {it.added_by === "sales" && (
            <div className="staff-tag"><Icon name="support_agent" size={14} /> พนักงานเพิ่มให้ · {it.added_by_name || "พนักงานขาย"}{it.added_by_code ? ` (${it.added_by_code})` : ""} · {thTime(it.added_at)}</div>
          )}
          <Link to={`/p/${it.matnr}`} className="cart-name">{it.name}</Link>
          {it.variant && <div className="small muted">{it.variant}</div>}
          {it.spec && <div className="small muted">{it.spec}</div>}
          <div className="cart-code">รหัสสินค้า: {it.matnr}</div>
          <StockTag it={it} />
          {it.pickup_only && <BranchPicker it={it} />}
          {it.note && <div className="small muted">หมายเหตุ: {it.note}</div>}
        </div>
        <div className="cart-tools">
          {/* วิธีรับสินค้า (ส่ง/ยกกลับ/ติดตั้ง) ย้ายไปเลือกทีเดียวที่หน้าชำระเงิน — ตรงนี้เลยเหลือแค่แก้ไขกับลบ */}
          <Link to={`/p/${it.matnr}`} className="icon-btn edit" title="แก้ไขรายการ" aria-label="แก้ไขรายการ"><Icon name="edit" size={18} /></Link>
          <button className="icon-btn danger" onClick={onRemove} disabled={busy} title="ลบออกจากตะกร้า" aria-label="ลบออกจากตะกร้า"><Icon name="delete" size={18} /></button>
        </div>
      </div>

      {/* ท้ายแถว: ราคา · จำนวน ชิดขวา (ยอดรวมรายบรรทัดตัดออก เพราะเท่ากับราคา × จำนวนที่เห็นอยู่แล้ว — ไปดูรวมทั้งหมดที่ช่องล่างสุด) */}
      <div className="cart-row-cols">
        <div className="cart-col">
          <span className="cart-col-lbl">ราคา</span>
          <b>{bahtWord(it.unit_price)}</b>
        </div>
        <div className="cart-col center">
          <span className="cart-col-lbl">จำนวน</span>
          <div className="qty sm">
            <button onClick={onDec} disabled={busy || it.qty <= 1} aria-label="ลด"><Icon name="remove" size={16} /></button>
            <span>{it.qty}</span>
            <button onClick={onInc} disabled={busy} aria-label="เพิ่ม"><Icon name="add" size={16} /></button>
          </div>
        </div>
      </div>
    </div>
  );
}
