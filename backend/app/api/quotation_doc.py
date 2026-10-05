"""เอกสารใบเสนอราคาแบบพิมพ์ได้ (mock ของ PDF — ของจริงต่อ PDF service)

แยกออกมาจาก api/quotation.py เพราะตัวมันโตขึ้นจนบังโค้ด endpoint ที่อยู่ไฟล์เดียวกัน

สองแบบ: มีรูปสินค้ากับไม่มี — เซลล์เลือกตอนกดจากหน้า Preso
  มีรูป    ใช้คุยกับลูกค้า เห็นภาพว่าซื้ออะไรอยู่
  ไม่มีรูป ใช้แนบอีเมล/ปรินต์ ไฟล์เล็กและกินหมึกน้อยกว่า
"""
import html
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.catalog import Material
from app.models.promo import AppliedDiscount
from app.models.quotation import Quotation

SUPPLY_TXT = {"takeaway": "ยกกลับ", "ship": "จัดส่ง", "install": "ส่ง+ติดตั้ง", "pickup": "รับที่สาขา"}
STATUS_TXT = {"issued": "ออกแล้ว · รอชำระ", "paid": "ชำระแล้ว", "converted": "สร้าง SO แล้ว",
              "cancelled": "ยกเลิก", "expired": "หมดอายุ"}


def _money(v) -> str:
    return f"{float(v):,.2f}"


def _image_map(db: Session, matnrs: list[str]) -> dict[str, str]:
    if not matnrs:
        return {}
    rows = db.execute(select(Material.matnr, Material.image_url).where(Material.matnr.in_(matnrs))).all()
    return {m: u for m, u in rows if u}


def render_document(db: Session, q: Quotation, with_images: bool = False) -> str:
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
    span = 6 if with_images else 5   # จำนวนคอลัมน์ก่อนช่อง "รวม"

    def item_row(i: int, l) -> str:
        cell = ""
        if with_images:
            u = imgs.get(l.matnr)
            pic = f'<img src="{e(u)}" alt="">' if u else ""
            cell = f"<td class='ph'>{pic}</td>"
        # ส่วนลดต่อบรรทัด = ราคาตั้ง − ราคาที่จ่ายจริง · เท่ากันแปลว่าไม่ได้ลด ไม่ต้องรก
        off = Decimal(l.list_price) - Decimal(l.unit_price)
        price = (f"<s class='muted'>{_money(l.list_price)}</s><br><b>{_money(l.unit_price)}</b>"
                 if off > 0 else _money(l.unit_price))
        disc = f"-{_money(off * l.qty)}" if off > 0 else "-"
        return (f"<tr><td>{i}</td>{cell}<td>{e(l.name)}<br><small class='muted'>{e(l.variant or '')} · MATNR {e(l.matnr)}</small></td>"
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
    sales_name = e(q.sales.name) if q.sales else "สั่งซื้อออนไลน์"
    sales_code = f" ({e(q.sales.staff_code)})" if q.sales and q.sales.staff_code else ""
    # ไม่มีเบอร์ก็ใช้อีเมล ไม่มีทั้งคู่ก็ไม่พิมพ์บรรทัดนั้น — "โทร -" คือช่องว่างที่กินที่
    # แล้วไม่ได้บอกอะไร ลูกค้าอ่านแล้วนึกว่าระบบพัง (ตั้งเบอร์ให้พนักงานด้วย cli.secure set-phone)
    contact = ""
    if q.sales and q.sales.phone:
        contact = f"<span class='muted'>โทร {e(q.sales.phone)}</span>"
    elif q.sales and q.sales.email:
        contact = f"<span class='muted'>{e(q.sales.email)}</span>"

    note = (q.preso.note if q.preso and q.preso.note else "").strip()
    note_block = (f"<div class='note-box'><b>หมายเหตุ</b><div>{e(note)}</div></div>" if note
                  else "<div class='note-box'><b>หมายเหตุ</b><div class='blank'></div></div>")

    terms = []
    if s.quotation_payment_terms:
        terms.append(f"<div><b>เงื่อนไขการชำระเงิน</b><br>{e(s.quotation_payment_terms)}</div>")
    if s.company_bank_account_no:
        bank = " · ".join(x for x in [e(s.company_bank_name), e(s.company_bank_branch)] if x)
        terms.append(f"<div><b>ชำระโดยโอนเข้าบัญชี</b><br>{bank}<br>"
                     f"{e(s.company_bank_account_name)}<br><b>{e(s.company_bank_account_no)}</b></div>")
    terms_block = f"<div class='terms'>{''.join(terms)}</div>" if terms else ""

    img_css = ".ph{width:72px}.ph img{width:64px;height:64px;object-fit:cover;border-radius:4px;background:#f2f2f0}" if with_images else ""

    return f"""<!doctype html><html lang="th"><head><meta charset="utf-8"><title>ใบเสนอราคา {e(q.quotation_no)}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@400;600;700&display=swap" rel="stylesheet">
<style>body{{font-family:'Noto Sans Thai',sans-serif;color:#111;max-width:860px;margin:32px auto;padding:0 24px;font-size:14px}}h1{{font-size:22px;margin:0}}table{{width:100%;border-collapse:collapse;margin-top:16px}}th,td{{padding:8px 10px;border-bottom:1px solid #e0e0de;vertical-align:top;text-align:left}}th{{background:#f2f2f0;font-size:12px}}.r{{text-align:right}}.tot td{{font-weight:700;border-top:2px solid #111}}.box{{display:flex;justify-content:space-between;gap:24px;margin-top:16px}}.muted{{color:#777;font-size:12px}}.tag{{display:inline-block;padding:2px 8px;border-radius:4px;background:#111;color:#fff;font-size:12px}}.note-box{{margin-top:16px;border:1px solid #e0e0de;border-radius:6px;padding:10px 12px;font-size:13px}}.note-box .blank{{min-height:38px}}.terms{{display:flex;gap:32px;margin-top:18px;font-size:13px;border-top:1px solid #e0e0de;padding-top:14px}}{img_css}@media print{{body{{margin:0}}}}</style></head>
<body><div class="box"><div><h1>ใบเสนอราคา / Quotation</h1><div class="muted">SB Design Square · บริษัท เอส.บี.อุตสาหกรรมเครื่องเรือน จำกัด</div></div>
<div style="text-align:right"><div><b>{e(q.quotation_no)}</b> <span class="tag">{e(STATUS_TXT.get(q.status, q.status))}</span></div><div class="muted">ออกเมื่อ {q.issued_at.strftime('%d/%m/%Y %H:%M')} · ยืนราคาถึง <b>{q.valid_until.strftime('%d/%m/%Y')}</b></div></div></div>
<div class="box"><div><b>ลูกค้า</b><br>{e(c.get('name') or '')} · CUST {e(c.get('sap_customer_no') or '-')} · {e(c.get('tier') or 'ทั่วไป')}<br><span class="muted">{e(c.get('phone') or '')} · {e(c.get('email') or '')}</span><br><span class="muted">{e(q.ship_address or '')} {e(q.ship_postcode or '')}</span></div>
<div style="text-align:right"><b>พนักงานขาย</b><br>{sales_name}{sales_code}{f"<br>{contact}" if contact else ""}</div></div>
{note_block}
<table><thead><tr><th>#</th>{img_col}<th>รายการ</th><th class="r">จำนวน</th><th class="r">ราคา/หน่วย</th><th class="r">ส่วนลด</th><th class="r">รวม</th><th>รับสินค้า</th></tr></thead><tbody>{rows}
<tr><td colspan="{span}" class="r">รวมสินค้า</td><td class="r">{_money(q.subtotal)}</td><td></td></tr>{disc_rows}
{fee_row}
<tr class="tot"><td colspan="{span}" class="r">รวมสุทธิ (รวม VAT 7% = {_money(q.vat)})</td><td class="r">{_money(q.grand_total)}</td><td></td></tr>
{dep_row}</tbody></table>
{terms_block}
<p class="muted">เอกสารนี้สร้างจากระบบ SB Sales App (mock PDF) · ราคาและโปรโมชั่นถูกล็อกไว้จนถึงวันยืนราคา · เมื่อชำระเงินสำเร็จ ระบบจะส่งใบเสนอราคาไป convert เป็น Sales Order ใน SAP{(' · SO ' + e(q.sap_so_no)) if q.sap_so_no else ''}</p>
</body></html>"""
