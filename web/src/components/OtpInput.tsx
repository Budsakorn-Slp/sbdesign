import { useEffect, useRef, type ClipboardEvent, type KeyboardEvent } from "react";

const LEN = 6;

/** ช่องกรอก OTP แบบแยกช่องต่อหลัก
 *
 * ทำไมถึงคุ้มกว่าช่องเดียว: เห็นทันทีว่ากรอกไปกี่หลักแล้วเหลืออีกกี่หลัก · แตะแก้หลักที่ผิด
 * ได้ตรงๆ ไม่ต้องเลื่อน cursor · และบนมือถือตัวเลขไม่ติดกันจนอ่านพลาด
 *
 * เก็บค่าเป็น string เดียวข้างนอก (ไม่ใช่ array ต่อช่อง) — การวาง/ลบทั้งชุดจึงไม่ต้อง
 * ไล่ sync หลายตัวแปร และผู้เรียกส่งเข้า API ได้เลยโดยไม่ต้องต่อสตริงเอง
 */
export default function OtpInput({
  value,
  onChange,
  disabled,
  autoFocus,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  autoFocus?: boolean;
}) {
  const boxes = useRef<(HTMLInputElement | null)[]>([]);
  const digits = value.replace(/\D/g, "").slice(0, LEN).split("");

  useEffect(() => {
    if (autoFocus) boxes.current[0]?.focus();
  }, [autoFocus]);

  const focus = (i: number) => boxes.current[Math.max(0, Math.min(LEN - 1, i))]?.focus();

  const setAt = (i: number, digit: string) => {
    const next = value.replace(/\D/g, "").slice(0, LEN).padEnd(LEN, " ").split("");
    next[i] = digit || " ";
    onChange(next.join("").replace(/ /g, "").slice(0, LEN));
  };

  const onKey = (i: number) => (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace") {
      e.preventDefault();
      // ช่องว่างอยู่แล้ว = ถอยไปลบช่องก่อนหน้า (พฤติกรรมที่คนคาดหวังจากช่องแยก)
      if (digits[i]) setAt(i, "");
      else if (i > 0) {
        setAt(i - 1, "");
        focus(i - 1);
      }
      return;
    }
    if (e.key === "ArrowLeft") return focus(i - 1);
    if (e.key === "ArrowRight") return focus(i + 1);
  };

  // วางรหัสทั้งชุดจาก SMS ทีเดียว — เป็นวิธีที่คนใช้จริงมากกว่าพิมพ์ทีละหลัก
  const onPaste = (e: ClipboardEvent<HTMLInputElement>) => {
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, LEN);
    if (!pasted) return;
    e.preventDefault();
    onChange(pasted);
    focus(pasted.length);
  };

  return (
    <div className="otp-boxes" role="group" aria-label="รหัสยืนยัน 6 หลัก">
      {Array.from({ length: LEN }, (_, i) => (
        <input
          key={i}
          ref={(el) => {
            boxes.current[i] = el;
          }}
          className={"otp-box" + (digits[i] ? " filled" : "")}
          value={digits[i] || ""}
          onChange={(e) => {
            const d = e.target.value.replace(/\D/g, "").slice(-1);
            if (!d) return;
            setAt(i, d);
            focus(i + 1);
          }}
          onKeyDown={onKey(i)}
          onPaste={onPaste}
          onFocus={(e) => e.target.select()}
          inputMode="numeric"
          autoComplete={i === 0 ? "one-time-code" : "off"}
          maxLength={1}
          disabled={disabled}
          aria-label={`หลักที่ ${i + 1}`}
        />
      ))}
    </div>
  );
}
