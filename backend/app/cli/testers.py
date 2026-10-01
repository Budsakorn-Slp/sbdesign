"""จัดการบัญชีผู้ทดสอบ — ใช้ช่วง invite_only (ก่อนเปิดให้คนทั่วไปสมัคร)

ทำไมต้องมี:
  พอเปิด INVITE_ONLY=true ระบบจะไม่สร้างบัญชีใหม่ให้ใครอีก (ดู auth_service._refuse_signup_if_invite_only)
  คนที่จะเข้าไปทดสอบได้จึงต้องมีบัญชีอยู่ก่อนแล้ว — ไฟล์นี้คือเครื่องมือสร้างบัญชีพวกนั้น

ใช้ยังไง (รันในโฟลเดอร์ backend):
  python -m app.cli.testers list
  python -m app.cli.testers add 0812345678 --name "คุณเอ" --password 1122
  python -m app.cli.testers add 0812345678 --member 1100440182     # ผูกเลขสมาชิก SAP ให้เลย
  python -m app.cli.testers remove 0812345678

หมายเหตุ:
  * ใส่ --password ให้ด้วยจะดีกว่า เพราะช่วงทดสอบ SMS จริงอาจยังไม่ได้ต่อ
    ผู้ทดสอบจะได้เข้าด้วย เบอร์ + รหัสผ่าน โดยไม่ต้องรอ OTP
  * remove ไม่ได้ลบข้อมูลทิ้ง แค่เปลี่ยนเบอร์ให้เข้าไม่ได้ (กันข้อมูลตะกร้า/ใบเสนอราคาหาย)
  * เบอร์จริงของทีมไม่ต้องเอามาใส่ก็ได้ ใช้เบอร์สมมุติ 08xxxxxxxx ได้เลย
    เพราะช่วงนี้เข้าด้วยรหัสผ่าน ไม่ได้ส่ง SMS ไปที่เบอร์นั้นจริง
"""
import argparse
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.common import utcnow
from app.models.user import User
from app.services.auth_service import normalize_phone


def _find(db, phone: str) -> User | None:
    return db.scalar(select(User).where(User.phone == normalize_phone(phone)))


def cmd_list(_args) -> int:
    with SessionLocal() as db:
        rows = db.scalars(select(User).where(User.role == "customer", User.phone.is_not(None))
                          .order_by(User.created_at.desc())).all()
        if not rows:
            print("ยังไม่มีบัญชีลูกค้าเลย")
            return 0
        print(f"{'เบอร์':<14} {'ชื่อ':<24} {'เลขสมาชิก':<12} รหัสผ่าน")
        for u in rows:
            print(f"{u.phone or '-':<14} {(u.name or '-')[:24]:<24} "
                  f"{u.sap_customer_no or '-':<12} {'ตั้งแล้ว' if u.password_hash else 'ยังไม่ตั้ง (ต้องใช้ OTP)'}")
    return 0


def cmd_add(args) -> int:
    """ใส่ได้หลายเบอร์ในครั้งเดียว — ตั้งทีมทดสอบทั้งชุดจบในคำสั่งเดียว"""
    bad = 0
    for phone in args.phone:
        bad += _add_one(args, phone)
    return 1 if bad else 0


def _add_one(args, phone: str) -> int:
    digits = normalize_phone(phone)
    if len(digits) != 10:
        print(f"! เบอร์ต้องมี 10 หลัก (ได้ {digits!r})")
        return 1
    with SessionLocal() as db:
        u = _find(db, digits)
        if u:
            print(f"มีบัญชีนี้อยู่แล้ว: {u.name} ({u.phone}) — จะอัปเดตข้อมูลที่ระบุมาให้")
        else:
            u = User(role="customer", phone=digits, is_guest=False,
                     name=args.name or f"ผู้ทดสอบ {digits[-4:]}")
            db.add(u)
        if args.name:
            u.name = args.name
        if args.member:
            u.sap_customer_no = args.member
        if args.password:
            u.password_hash = hash_password(args.password)
        # ถือว่ายืนยันเบอร์แล้ว ไม่ต้องให้ผู้ทดสอบไปวนขอ OTP ก่อนใช้งาน
        u.phone_verified_at = utcnow()
        # ข้ามหน้าตั้งค่าบัญชีครั้งแรก เข้าไปถึงหน้าร้านได้เลย
        u.onboarded_at = utcnow()
        db.commit()
        print(f"พร้อมใช้งาน: {u.name} · {u.phone}"
              + (f" · เลขสมาชิก {u.sap_customer_no}" if u.sap_customer_no else "")
              + (" · เข้าด้วยรหัสผ่านได้" if u.password_hash else " · ยังไม่มีรหัสผ่าน ต้องเข้าด้วย OTP"))
    return 0


def cmd_remove(args) -> int:
    with SessionLocal() as db:
        u = _find(db, args.phone)
        if not u:
            print("ไม่พบเบอร์นี้")
            return 1
        # ไม่ลบแถวทิ้ง — ตะกร้า ใบเสนอราคา และ log ผูกกับ user นี้อยู่
        # ปลดเบอร์กับรหัสผ่านออกก็พอ เข้าไม่ได้แล้วแต่ประวัติยังตรวจย้อนหลังได้
        old = u.phone
        u.phone = None
        u.password_hash = None
        db.commit()
        print(f"ปิดการเข้าใช้ของ {old} แล้ว (ข้อมูลเดิมยังอยู่ ไม่ได้ลบ)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli.testers", description="จัดการบัญชีผู้ทดสอบช่วง invite_only")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="ดูบัญชีลูกค้าทั้งหมดที่เข้าได้").set_defaults(fn=cmd_list)

    a = sub.add_parser("add", help="สร้าง/อัปเดตบัญชีผู้ทดสอบ")
    a.add_argument("phone", nargs="+", help="เบอร์ 10 หลัก ใส่ได้หลายเบอร์คั่นด้วยเว้นวรรค")
    a.add_argument("--name", help="ชื่อที่จะแสดง")
    a.add_argument("--password", help="รหัสผ่านสำหรับเข้าระบบโดยไม่ต้องรอ OTP")
    a.add_argument("--member", help="เลขสมาชิก SAP ถ้าอยากให้ผูกบัตรไว้เลย")
    a.set_defaults(fn=cmd_add)

    r = sub.add_parser("remove", help="ปิดไม่ให้เบอร์นี้เข้าระบบ (ไม่ลบข้อมูล)")
    r.add_argument("phone")
    r.set_defaults(fn=cmd_remove)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
