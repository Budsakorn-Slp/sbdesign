"""เอกสารใบเสนอราคาแบบพิมพ์ได้ (mock ของ PDF — ของจริงต่อ PDF service)

แยกออกมาจาก api/quotation.py เพราะตัวมันโตขึ้นจนบังโค้ด endpoint ที่อยู่ไฟล์เดียวกัน

สองแบบ: มีรูปสินค้ากับไม่มี — เซลล์เลือกตอนกดจากหน้า Preso
  มีรูป    ใช้คุยกับลูกค้า เห็นภาพว่าซื้ออะไรอยู่
  ไม่มีรูป ใช้แนบอีเมล/ปรินต์ ไฟล์เล็กและกินหมึกน้อยกว่า
"""
import html
from urllib.parse import quote
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.catalog import Material
from app.models.promo import AppliedDiscount
from app.models.quotation import Quotation

COMPANY_LOGO = "https://media.sbdesignsquare.com/media/logo/stores/2/Logo_header_newsb_1.png"

SUPPLY_TXT = {"takeaway": "ยกกลับ", "ship": "จัดส่ง", "install": "ส่ง+ติดตั้ง", "pickup": "รับที่สาขา"}
STATUS_TXT = {"issued": "ออกแล้ว · รอชำระ", "paid": "ชำระแล้ว", "converted": "สร้าง SO แล้ว",
              "cancelled": "ยกเลิก", "expired": "หมดอายุ"}


# เงื่อนไขท้ายใบเสนอราคา — ข้อความมาตรฐานของบริษัท
#
# เก็บเป็นโค้ดไม่ใช่ .env เพราะมันยาวหลายบรรทัดและมีเลขบัญชีที่ต้องถูกต้องเป๊ะ
# ยัดลง .env แล้วจะอ่านไม่ออกและแก้ผิดง่าย · อยากเขียนทับทั้งก้อนใช้ QUOTATION_TERMS ได้
# {month_end} ถูกแทนด้วย "วันสุดท้ายของเดือนที่ออกใบ" ตอนพิมพ์ — ห้ามเขียนวันที่ตายตัว
# ไม่งั้นทุกใบจะบอกวันของใบแรกที่เคยออก · คนละเรื่องกับวันยืนราคา (valid_until) บนหัวใบ
# ยังใช้ {valid_until} ได้ถ้าอยากอ้างวันยืนราคา
DEFAULT_TERMS = [
    "ใบเสนอราคานี้มีกำหนดอายุถึงวันที่ {month_end} หรือตามกำหนดเวลาที่ระบุในโปรโมชั่นของบริษัท",
    "บริษัทฯ อาจมีการเรียกเก็บค่าขนส่งสินค้า นอกเขตพื้นที่การให้บริการ สอบถามรายละเอียดได้จากพนักงานขาย",
    "การชำระเงิน : รับชำระเป็น เงินสด, แคชเชียร์เช็ค, บัตรเครดิต หรือ โอนเงิน\n"
    'ชื่อบัญชี "บริษัท เอสบี ดีไซน์สแควร์ จำกัด"\n'
    "ธ.กรุงเทพ เลขที่ 207-4-23928-2 บัญชีออมทรัพย์ สาขาปากเกร็ด\n"
    "ธ.กสิกรไทย เลขที่ 142-1-06853-0 บัญชีกระแสรายวัน สาขาปากเกร็ด\n"
    "ธ.ไทยพาณิชย์ เลขที่ 305-3-02510-4 บัญชีกระแสรายวัน สาขาปากเกร็ด",
    "ลูกค้าเป็นผู้จัดเตรียม พื้นที่ให้พร้อมในการติดตั้ง",
    "การรับประกันสินค้า เป็นไปตามเงื่อนไขที่บริษัทกำหนด ดูรายละเอียดการรับประกันได้ที่ www.sbdesignsquare.com",
    "อื่นๆ ..",
]


def _fill(t: str, valid_until: str, month_end: str) -> str:
    # replace ไม่ใช่ format — ข้อความที่ DS พิมพ์เองอาจมีปีกกาอื่นปนมา format จะพัง
    return t.replace("{valid_until}", valid_until).replace("{month_end}", month_end)


def _terms(valid_until: str, month_end: str, custom: str | None = None) -> list[str]:
    """custom = เงื่อนไขจาก template ของ DS (บรรทัดละข้อ) · ว่าง = ค่ากลางของบริษัท"""
    if custom and custom.strip():
        items = [t.strip() for t in custom.splitlines() if t.strip()]
    else:
        raw = get_settings().quotation_terms
        items = [t.strip() for t in raw.replace(";", "\n").split("|") if t.strip()] if raw else DEFAULT_TERMS
    return [_fill(t, valid_until, month_end) for t in items]


def month_end_of(q: Quotation) -> str:
    """วันท้ายบิลของใบนี้ — ใบใหม่เก็บไว้ใน template_snapshot ใบเก่าคำนวณจากวันออก"""
    from app.services.sales_extras_service import month_end

    tp = q.template_snapshot or {}
    if tp.get("month_end"):
        return date.fromisoformat(tp["month_end"]).strftime("%d/%m/%Y")
    return month_end(q.issued_at.date()).strftime("%d/%m/%Y")


def _money(v) -> str:
    return f"{float(v):,.2f}"


def _image_map(db: Session, matnrs: list[str]) -> dict[str, str]:
    if not matnrs:
        return {}
    rows = db.execute(select(Material.matnr, Material.image_url).where(Material.matnr.in_(matnrs))).all()
    return {m: u for m, u in rows if u}


def render_document(db: Session, q: Quotation, with_images: bool = False, proxy_images: bool = False) -> str:
    e = html.escape
    s = get_settings()
    c = q.customer_snapshot or {}

    # บรรทัดค่าบริการที่เซลล์ "เปิด Mat" ไว้ (A534 ฯลฯ) ไม่ใช่สินค้า — แยกออกจากตารางสินค้า
    # ของเดิมปนอยู่ด้วยกัน ลูกค้าเลยเห็นค่าขนส่งสองรอบ: ครั้งหนึ่งเป็นบรรทัดสินค้า
    # อีกครั้งในช่อง "ค่าขนส่ง" ข้างล่าง ทั้งที่ยอดรวมนับครั้งเดียว
    from app.services import staff_shipping_service

    charges = staff_shipping_service.charge_matnrs()
    items = [l for l in q.lines if l.matnr not in charges]
    fee_lines = [l for l in q.lines if l.matnr in charges]

    imgs = _image_map(db, [l.matnr for l in items]) if with_images else {}
    img_col = "<th></th>" if with_images else ""
    # # · [รูป] · รหัสสินค้า · รายการ · จำนวน · ราคา/หน่วย · ส่วนลด = คอลัมน์ก่อนช่อง "รวม"
    span = 6 + (1 if with_images else 0)

    def item_row(i: int, l) -> str:
        cell = ""
        if with_images:
            u = imgs.get(l.matnr)
            # proxy = ดึงรูปผ่านเซิร์ฟเวอร์เรา — ตอนสร้างไฟล์ PDF ในเบราว์เซอร์ รูปจากเว็บหลัก (ไม่เปิด CORS)
            # จะวาดลงไฟล์ไม่ได้ ต้องเป็นรูปจากโดเมนเดียวกัน · ลิงก์ relative ไปถูกทั้ง /api และตรงที่ API
            src = f"../../media-proxy?url={quote(u, safe='')}" if (proxy_images and u) else u
            pic = f'<img src="{e(src)}" alt="">' if u else ""
            cell = f"<td class='ph'>{pic}</td>"
        # ส่วนลดต่อบรรทัด = ราคาตั้ง − ราคาที่จ่ายจริง · เท่ากันแปลว่าไม่ได้ลด ไม่ต้องรก
        off = Decimal(l.list_price) - Decimal(l.unit_price)
        price = (f"<s class='muted'>{_money(l.list_price)}</s><br><b>{_money(l.unit_price)}</b>"
                 if off > 0 else _money(l.unit_price))
        disc = f"-{_money(off * l.qty)}" if off > 0 else "-"
        # รหัสสินค้าแยกคอลัมน์ ไม่ใช่ตัวเล็กต่อท้ายชื่อ — คนคลังกับฝ่ายบัญชีไล่ทีละรหัส
        # การต้องกวาดตาหาเลขที่ซ่อนอยู่ท้ายชื่อยาวๆ ทำให้อ่านผิดบรรทัดได้ง่าย
        sub = f"<br><small class='muted'>{e(l.variant)}</small>" if l.variant else ""
        if l.item_remark:
            sub += f"<br><small class='rmk'>หมายเหตุ: {e(l.item_remark)}</small>"
        return (f"<tr><td>{i}</td>{cell}<td class='mono'>{e(l.matnr)}</td><td>{e(l.name)}{sub}</td>"
                f"<td class='r'>{l.qty}</td><td class='r'>{price}</td><td class='r'>{disc}</td>"
                f"<td class='r'>{_money(l.line_total)}</td><td>{e(SUPPLY_TXT.get(l.supply_mode, l.supply_mode))}</td></tr>")

    rows = "".join(item_row(i + 1, l) for i, l in enumerate(items))

    discs = db.scalars(select(AppliedDiscount).where(AppliedDiscount.quotation_id == q.id)).all()
    # ส่วนลดยอด 0 ไม่ต้องพิมพ์ — "ส่งฟรีในเขต กทม. 0.00" คู่กับ "ค่าขนส่ง 600" อ่านแล้วขัดกันเอง
    # ส่วนลดค่าส่งที่มีค่าจริงถูกหักในช่องค่าขนส่งอยู่แล้ว เอามาตั้งอีกแถวจะกลายเป็นหักซ้ำในสายตาคนอ่าน
    disc_rows = "".join(
        f"<tr><td colspan='{span}' class='r'>{e(d.title or d.promo_code or d.kind)}</td><td class='r'>-{_money(d.amount)}</td><td></td></tr>"
        for d in discs if float(d.amount) > 0
    )

    fee_total = float(q.shipping_fee) + float(q.install_fee) - float(q.shipping_discount)
    fee_note = ""
    if fee_lines:
        fee_note = " · " + " · ".join(f"{e(l.name)} (MATNR {e(l.matnr)})" for l in fee_lines)
    fee_row = (f"<tr><td colspan='{span}' class='r'>ค่าขนส่ง{' + ติดตั้ง' if float(q.install_fee) else ''}"
               f"<span class='muted'>{fee_note}</span></td><td class='r'>{_money(fee_total)}</td><td></td></tr>")
    if float(q.shipping_discount) > 0:
        fee_row = (f"<tr><td colspan='{span}' class='r'>ค่าขนส่ง{' + ติดตั้ง' if float(q.install_fee) else ''}"
                   f"<span class='muted'> (หักส่วนลดค่าส่ง {_money(q.shipping_discount)} แล้ว){fee_note}</span></td>"
                   f"<td class='r'>{_money(fee_total)}</td><td></td></tr>")

    dep_row = (f"<tr><td colspan='{span}' class='r muted'>มัดจำ 20% วันนี้ · ที่เหลือชำระวันส่ง</td>"
               f"<td class='r muted'>{_money(q.deposit_amount)}</td><td></td></tr>"
               if s.deposit_enabled else "")

    # เบอร์พนักงานขาย ไม่ใช่คิวจัดส่ง — ลูกค้าถือใบนี้แล้วอยากโทรถามคนที่คุยด้วย
    # คิวจัดส่งเปลี่ยนได้หลังออกใบ เอาไปพิมพ์ค้างไว้จะกลายเป็นข้อมูลผิดในมือลูกค้า
    # template ของ DS (ถ้ามี) ทับค่าจากบัญชี — ชื่อที่อยากให้ลูกค้าเห็น เบอร์ที่ใช้ติดต่องาน
    tp = q.template_snapshot or {}
    sales_name = e(tp.get("employee_name") or (q.sales.name if q.sales else "สั่งซื้อออนไลน์"))
    sales_code = f" ({e(q.sales.staff_code)})" if q.sales and q.sales.staff_code else ""
    # ไม่มีเบอร์ก็ใช้อีเมล ไม่มีทั้งคู่ก็ไม่พิมพ์บรรทัดนั้น — "โทร -" คือช่องว่างที่กินที่
    # แล้วไม่ได้บอกอะไร ลูกค้าอ่านแล้วนึกว่าระบบพัง (ตั้งเบอร์ให้พนักงานด้วย cli.secure set-phone)
    contact = ""
    if tp.get("phone"):
        contact = f"<span class='muted'>โทร {e(tp['phone'])}</span>"
    elif q.sales and q.sales.phone:
        contact = f"<span class='muted'>โทร {e(q.sales.phone)}</span>"
    elif q.sales and q.sales.email:
        contact = f"<span class='muted'>{e(q.sales.email)}</span>"

    # ที่อยู่ออกบิลมาจากทะเบียนลูกค้า ที่อยู่ส่งของมาจากที่กรอกตอนคำนวณค่าส่ง — คนละช่องกัน
    # ไม่มีที่อยู่ออกบิลก็ใช้ที่อยู่ส่งของแทน ดีกว่าปล่อยช่องว่างให้ดูเหมือนข้อมูลหาย
    bill_addr = " ".join(x for x in [e(c.get("address") or ""), e(c.get("postcode") or "")] if x).strip()
    ship_addr = " ".join(x for x in [e(q.ship_address or ""), e(q.ship_postcode or "")] if x).strip()
    bill_addr = bill_addr or ship_addr or "<i>ไม่มีข้อมูล</i>"
    ship_addr = ship_addr or "<i>ยังไม่ได้ระบุ</i>"

    # สาขาที่ออกใบ = สาขาที่พนักงานขายคนนั้นสังกัด (ตั้งด้วย cli.secure set-branch)
    # ใบรับคำสั่งซื้อของระบบเดิมพิมพ์ "319-DS. บางแค" ไว้มุมขวาบน ลูกค้าจะได้รู้ว่าติดต่อร้านไหน
    br = ""
    b_code = tp.get("branch_code") or (q.sales.branch_id if q.sales else None)
    b_name = tp.get("branch_name") or (q.sales.branch_name if q.sales else None)
    if b_name:
        code = (b_code or "").lstrip("S")   # ของเดิมพิมพ์ 319 ไม่ใช่ S319
        br = f"{e(code)} · {e(b_name)}"

    # พนักงานร่วมบิล Z1-ZK
    staff_block = ""
    if q.staff_snapshot:
        cells = "".join(f"<span><b>{e(r['role_code'])}</b> {e(r.get('role_name') or '')}: "
                        f"{e(r['employee_code'])} – {e(r['employee_name'])}</span>" for r in q.staff_snapshot)
        staff_block = f"<div class='staff'>{cells}</div>"

    # โลโก้ของ DS · ลิงก์แบบ relative เพราะเอกสารนี้เปิดได้ทั้งตรงที่ API (/quotations/..)
    # และผ่านหน้าเว็บ (/api/quotations/..) — "../../media" ไปถูกที่ทั้งสองทาง
    # ไม่มีโลโก้ใน template ของ DS → ใช้โลโก้บริษัท · โหมด proxy ดึงผ่านเซิร์ฟเวอร์เราเพื่อให้วาดลง PDF ได้
    if tp.get("logo_path"):
        logo_src = f"../../media/{tp['logo_path']}"
    else:
        logo_src = f"../../media-proxy?url={quote(COMPANY_LOGO, safe='')}" if proxy_images else COMPANY_LOGO
    logo = f"<img class='logo' src='{e(logo_src)}' alt='SB Design Square'>"

    note = (q.overall_remark or (q.preso.note if q.preso and q.preso.note else "") or "").strip()
    std = (tp.get("standard_remark") or "").strip()
    if std:
        note = f"{note}\n{std}" if note else std
    note_block = (f"<div class='note-box'><b>หมายเหตุ</b><div>{e(note).replace(chr(10), '<br>')}</div></div>" if note
                  else "<div class='note-box'><b>หมายเหตุ</b><div class='blank'></div></div>")

    items = _terms(q.valid_until.strftime("%d/%m/%Y"), month_end_of(q), tp.get("footer_terms"))
    lis = "".join(f"<li>{e(t).replace(chr(10), '<br>')}</li>" for t in items)
    terms_block = f"<div class='terms'><b>เงื่อนไข</b><ol>{lis}</ol></div>" if items else ""
    bank = (tp.get("bank_accounts") or "").strip()
    if bank:
        terms_block += f"<div class='terms'><b>บัญชีสำหรับโอนชำระ</b><div>{e(bank).replace(chr(10), '<br>')}</div></div>"

    img_css = ".ph{width:72px}.ph img{width:64px;height:64px;object-fit:cover;border-radius:4px;background:#f2f2f0}" if with_images else ""

    return f"""<!doctype html><html lang="th"><head><meta charset="utf-8"><title>ใบเสนอราคา {e(q.quotation_no)}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@400;600;700&display=swap" rel="stylesheet">
<style>body{{font-family:'Noto Sans Thai',sans-serif;color:#111;max-width:860px;margin:32px auto;padding:0 24px;font-size:14px}}h1{{font-size:22px;margin:0}}table{{width:100%;border-collapse:collapse;margin-top:16px}}th,td{{padding:8px 10px;border-bottom:1px solid #e0e0de;vertical-align:top;text-align:left}}th{{background:#f2f2f0;font-size:12px}}.r{{text-align:right}}.mono{{font-family:ui-monospace,'Courier New',monospace;font-size:13px;white-space:nowrap}}.tot td{{font-weight:700;border-top:2px solid #111}}tbody tr:last-child td{{border-bottom:none}}.box{{display:flex;justify-content:space-between;gap:24px;margin-top:16px}}.box.three>div{{flex:1}}.muted{{color:#777;font-size:12px}}.tag{{display:inline-block;padding:2px 8px;border-radius:4px;background:#111;color:#fff;font-size:12px}}.note-box{{margin-top:16px;border:1px solid #e0e0de;border-radius:6px;padding:10px 12px;font-size:13px}}.note-box .blank{{min-height:38px}}.terms{{margin-top:18px;font-size:12px}}.terms ol{{margin:6px 0 0;padding-left:20px}}.terms li{{margin-bottom:6px;line-height:1.6}}.rmk{{color:#a15c00}}.logo{{width:110px;max-height:70px;object-fit:contain;flex:none}}.hdr{{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;padding-bottom:14px;border-bottom:2px solid #111}}.hdr-co{{display:flex;gap:14px;align-items:flex-start}}.co-txt{{font-size:11.5px;line-height:1.55;color:#333}}.co-txt b{{color:#111;font-size:12.5px}}.hdr-doc{{text-align:right;min-width:250px}}.hdr-doc h1{{font-size:26px;line-height:1.1}}.hdr-doc .sub{{color:#777;font-size:12px;margin-bottom:8px}}.meta{{width:auto;margin:0 0 0 auto}}.meta th,.meta td{{padding:2px 0 2px 14px;border:0;background:none;font-size:12.5px;text-align:right;white-space:nowrap}}.meta th{{color:#777;font-weight:400}}.parties{{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:16px;font-size:13px;line-height:1.6}}.parties .ttl{{display:block;margin-bottom:2px;font-size:13.5px}}.who{{display:flex;flex-wrap:wrap;gap:6px 40px;margin-top:14px;padding:8px 0;border-top:1px solid #e0e0de;border-bottom:1px solid #e0e0de;font-size:13px}}.who b{{margin-right:6px}}.staff{{margin-top:10px;display:flex;flex-wrap:wrap;gap:6px 18px;font-size:12px}}{img_css}@media print{{body{{margin:0}}.no-print{{display:none!important}}}}</style></head>
<body><div class="hdr">
<div class="hdr-co">{logo}<div class="co-txt"><b>{e(s.company_name_th)}</b><br><b>{e(s.company_name_en)}</b><br>{e(s.company_address_th)}<br>{e(s.company_address_en)}<br>เลขประจำตัวผู้เสียภาษี TAX ID {e(s.company_tax_id)}</div></div>
<div class="hdr-doc"><h1>ใบเสนอราคา</h1><div class="sub">Quotation</div>
<table class="meta">{f"<tr><th>สาขา</th><td>{br}</td></tr>" if br else ""}<tr><th>เลขที่ใบเสนอราคา</th><td><b>{e(q.quotation_no)}</b></td></tr><tr><th>วันที่ออก</th><td>{q.issued_at.strftime('%d/%m/%Y')}</td></tr><tr><th>ยืนราคาถึง</th><td><b>{q.valid_until.strftime('%d/%m/%Y')}</b></td></tr><tr><th>สถานะ</th><td><span class="tag">{e(STATUS_TXT.get(q.status, q.status))}</span></td></tr></table></div>
</div>
<div class="parties">
<div><b class="ttl">ชื่อ-ที่อยู่ลูกค้า</b><div>{e(c.get('name') or '')}</div><div>{bill_addr}</div><div>{e(c.get('phone') or '')}{(' · ' + e(c.get('email'))) if c.get('email') else ''}</div></div>
<div><b class="ttl">ชื่อ-สถานที่ส่งสินค้า</b><div>{e(c.get('name') or '')}</div><div>{ship_addr}</div>{f"<div>Tel. {e(c.get('phone'))}</div>" if c.get('phone') else ""}</div>
</div>
<div class="who"><span><b>รหัสลูกค้า</b> {e(c.get('sap_customer_no') or '-')}</span><span><b>พนักงานขาย</b> {sales_name}{sales_code}{f" · {contact}" if contact else ""}</span></div>
{staff_block}
{note_block}
<table><thead><tr><th>ลำดับ</th>{img_col}<th>รหัสสินค้า</th><th>รายการ</th><th class="r">จำนวน</th><th class="r">ราคาต่อหน่วย</th><th class="r">ส่วนลด</th><th class="r">จำนวนเงิน</th><th>รับสินค้า</th></tr></thead><tbody>{rows}
<tr><td colspan="{span}" class="r">รวมสินค้า</td><td class="r">{_money(q.subtotal)}</td><td></td></tr>{disc_rows}
{fee_row}
<tr class="tot"><td colspan="{span}" class="r">รวมสุทธิ (รวม VAT 7% = {_money(q.vat)})</td><td class="r">{_money(q.grand_total)}</td><td></td></tr>
{dep_row}</tbody></table>
{terms_block}
</body></html>"""
