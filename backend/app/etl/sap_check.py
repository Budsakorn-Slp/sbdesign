"""เครื่องมือเช็คสต็อกกับ SAP ด้วยมือ — ใช้ตรวจว่าเลขที่หน้าเว็บโชว์ตรงกับ SAP จริงไหม

วิธีใช้ (สั่งจากโฟลเดอร์ backend):

    .venv\\Scripts\\python.exe -m app.etl.sap_check 19217394 19248757

    ตัวเลือก
      --qty 1,2,500   จำนวนที่จะลองถาม (ค่าเริ่มต้น 1,2,500)
      --date 2026-09-16   วันที่อยากได้ของ (ค่าเริ่มต้น = วันนี้ + SAP_AVAIL_LEAD_DAYS)
      --customer 1100467950   รหัสลูกค้า (ค่าเริ่มต้น = walk-in ใน .env)
      --no-bill       ข้ามการทดสอบยิงรวมบิล

อ่านผลยังไง — จุดสำคัญอยู่ที่ "ยอดนิ่งหรือวิ่ง":
  ยอดนิ่ง = ขอ 1 กับ ขอ 500 ได้เลขเท่ากัน แปลว่าเป็นของที่มีจริง เชื่อได้
  ยอดวิ่ง = เลขเพิ่มตามที่ขอ แปลว่า SAP ยืนยันให้หมดโดยไม่เช็คของ เชื่อไม่ได้
            (เจอกับ 19248757 — ขอเท่าไหร่ตอบเท่านั้น +14 เสมอ)

ส่วนการทดสอบรวมบิลมีไว้จับสินค้าที่ "ทำทั้งบิลว่าง" ถ้าเจอตัวแบบนั้น เวลาลูกค้า
ใส่ตะกร้าปนกับตัวอื่น SAP จะไม่ตอบอะไรกลับมาเลย แล้วระบบต้องไปไล่ถามทีละบรรทัด
ซึ่งทุกบรรทัดจะเห็นของเต็มเหมือนกันหมด = เสี่ยงขายเกิน

ยิงกี่ครั้งก็ปลอดภัย เพราะเป็นการจำลองใบสั่งขาย (ORDER_NUMBER ว่าง) ไม่สร้างเอกสาร
และไม่จองของจริงใน SAP
"""
import argparse
import logging
from datetime import date, datetime, timedelta

from app.core.config import get_settings
from app.integrations.sap.availability import AvailAsk, get_availability_client
from app.integrations.sap.base import SapError


def _rows(client, matnr: str, qty: int, customer: str, req: date) -> list[dict]:
    return client._post([AvailAsk(matnr, qty)], customer, req)


def main() -> int:
    ap = argparse.ArgumentParser(description="เช็คสต็อกกับ SAP ด้วยมือ")
    ap.add_argument("matnrs", nargs="+", help="รหัสสินค้า เว้นวรรคได้หลายตัว")
    ap.add_argument("--qty", default="1,2,500")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD")
    ap.add_argument("--customer", default=None)
    ap.add_argument("--no-bill", action="store_true")
    a = ap.parse_args()

    logging.disable(logging.WARNING)  # log ของ client จะแทรกกลางตาราง อ่านยาก
    s = get_settings()
    client = get_availability_client()
    if type(client).__name__.startswith("Mock"):
        print("!! ตอนนี้ใช้ mock ไม่ได้ยิง SAP จริง — ตั้ง SAP_AVAIL_URL / SAP_API_KEY ใน .env ก่อน")
        return 2

    customer = a.customer or s.sap_walkin_customer
    req = datetime.strptime(a.date, "%Y-%m-%d").date() if a.date else date.today() + timedelta(days=s.sap_avail_lead_days)
    qtys = [int(q) for q in a.qty.split(",") if q.strip()]
    print(f"ถาม SAP ว่าส่งวันที่ {req} · ลูกค้า {customer}")

    verdict: dict[str, str] = {}
    for m in a.matnrs:
        print(f"\n=== {m}")
        seen: list[tuple[int, float]] = []
        for q in qtys:
            try:
                rows = _rows(client, m, q, customer, req)
            except SapError as e:
                print(f"  ขอ {q:<6} ยิงไม่ได้: {e}")
                continue
            if not rows:
                print(f"  ขอ {q:<6} SAP ไม่รู้จักรหัสนี้")
                verdict[m] = "SAP ไม่รู้จักรหัสนี้"
                break
            r = rows[0]
            seen.append((q, float(r["AVAILABLE_QUAN"])))
            print(
                f"  ขอ {q:<6} มีอยู่ {r['AVAILABLE_QUAN']:<10} จะเข้าอีก {r['COMMITTED_QUAN']:<10}"
                f" {r['COMMITTED_DATE'] or '-':<10} {r['DESCRIPTION']}"
            )
        if len(seen) >= 2:
            grows = seen[-1][1] - seen[0][1] == seen[-1][0] - seen[0][0]
            verdict[m] = "เลขวิ่งตามที่ขอ = เชื่อไม่ได้" if grows else f"ของมีจริง {seen[0][1]:.0f} ชิ้น"

    if not a.no_bill and len(a.matnrs) > 1:
        print("\n=== ทดสอบยิงรวมบิล (หาตัวที่ทำทั้งบิลว่าง)")
        try:
            asks = [AvailAsk(m, 1) for m in a.matnrs]
            got = len(client._post(asks, customer, req))
            print(f"  ขอ {len(asks)} บรรทัด ได้กลับมา {got} แถว", "— ปกติ" if got == len(asks) else "<<< ผิดปกติ")
            if got != len(asks):
                # ดึงออกทีละตัวไม่ได้ เพราะเหลือบรรทัดเดียวยังไงก็ผ่าน ต้องจับคู่ไขว้แทน
                # ตัวที่พังกับ "ทุก" คู่คือตัวการ ส่วนตัวที่เข้ากับตัวอื่นได้ถือว่าไม่ผิด
                bad_with: dict[str, int] = {m: 0 for m in a.matnrs}
                pairs = 0
                for i, m in enumerate(a.matnrs):
                    for o in a.matnrs[i + 1 :]:
                        pairs += 1
                        ok = len(client._post([AvailAsk(m, 1), AvailAsk(o, 1)], customer, req)) == 2
                        print(f"  {m} + {o} -> {'ปกติ' if ok else 'ว่าง'}")
                        if not ok:
                            bad_with[m] += 1
                            bad_with[o] += 1
                if len(a.matnrs) == 2:
                    print("  มีแค่ 2 รายการ ชี้ตัวการไม่ได้ — ใส่รหัสตัวที่สามที่ปกติเข้าไปด้วยแล้วรันซ้ำ")
                else:
                    others = len(a.matnrs) - 1
                    for m, n in bad_with.items():
                        if n == others:
                            print(f"  {m} พังกับทุกตัวที่จับคู่ -> ตัวการ")
                            verdict[m] = "ทำทั้งบิลว่างเมื่ออยู่กับตัวอื่น"
        except SapError as e:
            print("  ยิงไม่ได้:", e)

    print("\n=== สรุป")
    for m in a.matnrs:
        print(f"  {m}  {verdict.get(m, 'ดูตารางด้านบน')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
