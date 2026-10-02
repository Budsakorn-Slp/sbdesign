"""ตรวจความปลอดภัยและตั้งรหัสผ่านใหม่ — ใช้ก่อนเปิดให้คนนอกเข้า

    python -m app.cli.secure audit          # ตรวจอย่างเดียว ไม่แก้อะไร
    python -m app.cli.secure rotate         # ตั้งรหัสใหม่ให้บัญชีพนักงานที่รหัสอ่อน
    python -m app.cli.secure rotate --all   # ตั้งใหม่ทุกบัญชีพนักงาน ไม่ว่าอ่อนหรือไม่

ทำไมไม่พิมพ์รหัสออกหน้าจอ:
  หน้าจอถูกแคป ถูกแชร์ ถูกเก็บใน log ของ terminal และถูกเลื่อนขึ้นไปอ่านย้อนหลังได้
  รหัสใหม่จึงเขียนลงไฟล์ใน backend/secrets/ ซึ่งถูกกันออกจาก git แล้ว
  เปิดอ่าน ส่งให้เจ้าตัวทีละคน แล้วลบไฟล์ทิ้ง
"""
from __future__ import annotations

import argparse
import secrets
import string
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.db.session import SessionLocal
from app.models.user import User, UserSession
from app.models.common import utcnow

OUT_DIR = Path(__file__).resolve().parents[2] / "secrets"

# รหัสที่เดาได้ใน 1 นาที — ถ้าเจอตัวใดตัวหนึ่งถือว่าต้องเปลี่ยน
WEAK = ("1122", "1234", "123456", "password", "admin", "0000", "1111", "sb1234")

# ตัดอักขระที่อ่านผิดกันบ่อยออก (0/O, 1/l/I) เพราะรหัสนี้ต้องอ่านจากไฟล์แล้วพิมพ์ต่อ
ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")


def new_password(n: int = 14) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


def _weak_reason(u: User) -> str | None:
    if not u.password_hash:
        return "ยังไม่ได้ตั้งรหัสผ่าน"
    for p in WEAK:
        if verify_password(p, u.password_hash):
            return f"ใช้รหัสที่เดาได้ง่าย ({p})"
    return None


def cmd_audit(_args) -> int:
    s = get_settings()
    print("=== ตั้งค่าระบบ ===")
    checks = [
        ("APP_ENV=prod (ปิด /docs, cookie secure, HSTS)", s.is_prod),
        ("INVITE_ONLY=true (ปิดการสมัครเอง)", s.invite_only),
        ("JWT_SECRET ตั้งเองแล้ว", s.jwt_secret != "change-me-please-32-chars-minimum-secret" and len(s.jwt_secret) >= 32),
        ("OTP_DEBUG ปิด หรือจำกัดเบอร์แล้ว", (not s.otp_debug) or bool(s.otp_debug_phones.strip())),
        ("ไม่ได้เปิด SAP โหมดเขียนจริงโดยไม่ตั้งใจ", s.sap_mode == "mock" or bool(s.sap_so_url)),
    ]
    bad = 0
    for label, ok in checks:
        print(f"  {'ok  ' if ok else 'ต้องแก้'} {label}")
        bad += not ok

    print("\n=== บัญชีพนักงาน ===")
    with SessionLocal() as db:
        staff = db.scalars(select(User).where(User.role != "customer")).all()
        for u in staff:
            why = _weak_reason(u)
            print(f"  {'ต้องแก้' if why else 'ok  '} {u.staff_code or u.id:12} {u.role:8} {why or 'รหัสผ่านใช้ได้'}")
            bad += bool(why)

        cust = db.scalars(select(User).where(User.role == "customer", User.password_hash.is_not(None))).all()
        weak_cust = [u for u in cust if _weak_reason(u)]
        print(f"\n=== บัญชีลูกค้า ===\n  รหัสอ่อน {len(weak_cust)} จาก {len(cust)} บัญชี"
              " (ยอมรับได้ถ้าเป็นบัญชีทดสอบที่เราแจกรหัสเอง)")

    print(f"\nสรุป: {'ผ่านหมด' if not bad else f'ต้องแก้ {bad} ข้อ'}")
    return 1 if bad else 0


def cmd_rotate(args) -> int:
    """ตั้งรหัสใหม่ให้พนักงาน แล้วตัดทุก session ที่ค้างอยู่

    ตัด session ด้วยเพราะถ้ามีคนเคยเข้าบัญชีไปแล้ว การเปลี่ยนรหัสอย่างเดียวไม่ไล่เขาออก
    token ที่ถืออยู่ยังใช้ได้จนหมดอายุ
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = OUT_DIR / f"staff-passwords-{stamp}.txt"
    lines, changed = [], 0

    with SessionLocal() as db:
        staff = db.scalars(select(User).where(User.role != "customer").order_by(User.role, User.staff_code)).all()
        for u in staff:
            if not args.all and not _weak_reason(u):
                continue
            pw = new_password()
            u.password_hash = hash_password(pw)
            u.updated_at = utcnow()
            # ตัดอุปกรณ์ที่ค้างอยู่ทั้งหมด — เปลี่ยนรหัสแล้วแต่ token เดิมยังใช้ได้ = ยังไม่ปลอดภัย
            revoked = 0
            for sess in db.scalars(select(UserSession).where(UserSession.user_id == u.id, UserSession.revoked_at.is_(None))):
                sess.revoked_at = utcnow()
                revoked += 1
            lines.append(f"{u.staff_code or u.id}\t{u.role}\t{u.name}\t{pw}")
            changed += 1
            print(f"  ตั้งรหัสใหม่: {u.staff_code or u.id} ({u.role}) · ตัด session {revoked} อัน")
        db.commit()

    if not changed:
        print("ไม่มีบัญชีที่ต้องเปลี่ยน — รหัสพนักงานแข็งแรงอยู่แล้ว")
        return 0

    out.write_text(
        "รหัสผ่านพนักงานชุดใหม่ — ส่งให้เจ้าตัวทีละคนแล้วลบไฟล์นี้ทิ้ง\n"
        "ไฟล์นี้ถูกกันออกจาก git แล้ว อย่าส่งต่อทั้งไฟล์\n\n"
        "รหัสพนักงาน\tบทบาท\tชื่อ\tรหัสผ่าน\n" + "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    print(f"\nเปลี่ยนแล้ว {changed} บัญชี · รหัสใหม่อยู่ที่\n  {out}")
    print("เปิดอ่าน ส่งให้เจ้าตัว แล้วลบไฟล์ทิ้ง")
    return 0


def cmd_set_staff(args) -> int:
    """ตั้งรหัสพนักงานทุกบัญชีเป็นค่าที่ระบุ — สำหรับ "เครื่องทดสอบที่แจกรหัสเดียวกันทั้งทีม"

    ห้ามใช้กับของจริง · audit จะยังขึ้นเตือนถ้ารหัสอยู่ในรายการที่เดาง่าย ซึ่งถูกแล้ว
    """
    if get_settings().sap_mode != "mock":
        print("! ระบบต่อ SAP โหมดเขียนจริงอยู่ — ไม่ยอมตั้งรหัสง่ายให้")
        return 1
    with SessionLocal() as db:
        staff = db.scalars(select(User).where(User.role != "customer")).all()
        for u in staff:
            u.password_hash = hash_password(args.password)
            u.updated_at = utcnow()
            print(f"  {u.staff_code or u.id} ({u.role})")
        db.commit()
    print(f"\nตั้งรหัสพนักงาน {len(staff)} บัญชีเป็นค่าที่ระบุแล้ว")
    print("อย่าลืมเปลี่ยนก่อนขึ้นใช้งานจริง — ตรวจด้วย python -m app.cli.secure audit")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli.secure", description="ตรวจความปลอดภัยและตั้งรหัสใหม่")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("audit", help="ตรวจอย่างเดียว ไม่แก้อะไร").set_defaults(fn=cmd_audit)
    r = sub.add_parser("rotate", help="ตั้งรหัสใหม่ให้บัญชีพนักงานที่รหัสอ่อน")
    r.add_argument("--all", action="store_true", help="ตั้งใหม่ทุกบัญชีพนักงาน ไม่ว่าอ่อนหรือไม่")
    r.set_defaults(fn=cmd_rotate)
    ss = sub.add_parser("set-staff", help="ตั้งรหัสพนักงานทุกบัญชีเป็นค่าเดียวกัน (เครื่องทดสอบเท่านั้น)")
    ss.add_argument("--password", required=True)
    ss.set_defaults(fn=cmd_set_staff)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
