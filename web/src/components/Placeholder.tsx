import type { CSSProperties, ReactNode } from "react";

type Props = { label?: ReactNode; ratio?: string; className?: string; style?: CSSProperties; src?: string | null; alt?: string };

/** กรอบภาพแบบ wireframe (ลายทาง) — ถ้ามี src จะโชว์รูปจริงแทน */
export default function Placeholder({ label, ratio = "1 / 1", className, style, src, alt }: Props) {
  if (src) {
    return (
      <div className={"img-frame" + (className ? " " + className : "")} style={{ aspectRatio: ratio, ...style }}>
        <img src={src} alt={alt || ""} loading="lazy" />
      </div>
    );
  }
  return (
    <div className={"ph img" + (className ? " " + className : "")} style={{ aspectRatio: ratio, ...style }}>
      {label}
    </div>
  );
}
