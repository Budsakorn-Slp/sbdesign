"""ตัวบอกความคืบหน้าของงานที่รันนาน — พิมพ์ทับบรรทัดเดิม ไม่ไหลลงเป็นพรืด

งานอย่าง refresh_stock ยิง SAP 184 ครั้งใช้เวลา ~15 นาที ถ้าเงียบตลอดคนรันจะนึกว่าค้าง
แล้วกด Ctrl+C ทิ้งกลางคัน (เกิดขึ้นมาแล้ว) — บรรทัดเดียวที่ขยับอยู่บอกได้ว่ายังเดินอยู่
"""
from __future__ import annotations

import sys
import time


def _hhmm(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} วิ"
    if seconds < 3600:
        return f"{seconds // 60} นาที"
    return f"{seconds // 3600} ชม. {seconds % 3600 // 60} นาที"


class Progress:
    """พิมพ์ "ทำไปแล้ว x/y · เหลืออีก ~z" ทับบรรทัดเดิมเรื่อยๆ

    เวลาที่เหลือคิดจากอัตราจริงที่วัดได้ ไม่ใช่ค่าคงที่ที่เดาไว้ — งานยิง SAP เร็วช้า
    ไม่เท่ากันในแต่ละช่วงของวัน ขึ้นกับว่าระบบหลังบ้านว่างแค่ไหน
    """

    def __init__(self, total: int, label: str = "", *, stream=None):
        self.total = max(total, 1)
        self.label = label
        self.stream = stream or sys.stdout
        self.t0 = time.monotonic()
        self.done = 0
        self._tty = bool(getattr(self.stream, "isatty", lambda: False)())

    def step(self, n: int = 1) -> None:
        self.done = min(self.done + n, self.total)
        self._draw()

    def _draw(self) -> None:
        elapsed = time.monotonic() - self.t0
        rate = self.done / elapsed if elapsed > 0 else 0
        left = (self.total - self.done) / rate if rate > 0 else 0
        pct = self.done * 100 // self.total
        line = (f"  {self.label}{self.done:,}/{self.total:,} ({pct}%)"
                f" · {rate * 60:,.0f}/นาที · เหลืออีก ~{_hhmm(left)}")
        if self._tty:
            # ต่อท้ายด้วยช่องว่างกันเศษข้อความรอบก่อนค้างอยู่ตอนบรรทัดใหม่สั้นกว่าเดิม
            self.stream.write("\r" + line.ljust(78))
        else:
            # ไม่ใช่หน้าจอ (เขียนลงไฟล์ log / ตั้งเวลารันอัตโนมัติ) — \r ทำให้ log อ่านไม่ออก
            # พิมพ์เป็นบรรทัดแต่ห่างๆ พอให้รู้ว่ายังเดินอยู่ ไม่ท่วม log
            if self.done == self.total or self.done % max(self.total // 10, 1) < 1:
                self.stream.write(line + "\n")
        self.stream.flush()

    def close(self, note: str = "") -> None:
        elapsed = time.monotonic() - self.t0
        line = f"  {self.label}{self.done:,}/{self.total:,} · ใช้เวลา {_hhmm(elapsed)}{note}"
        if self._tty:
            self.stream.write("\r" + line.ljust(78) + "\n")
        else:
            self.stream.write(line + "\n")
        self.stream.flush()
