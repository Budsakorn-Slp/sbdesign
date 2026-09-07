import type { CSSProperties } from "react";

type Props = { name: string; size?: number; style?: CSSProperties; className?: string; fill?: boolean };

/** Material Symbols Rounded (โหลดจาก Google Fonts ใน index.html) */
export default function Icon({ name, size = 22, style, className, fill }: Props) {
  return (
    <span
      className={"ms" + (className ? " " + className : "")}
      aria-hidden="true"
      style={{ fontSize: size, fontVariationSettings: fill ? "'FILL' 1" : "'FILL' 0", ...style }}
    >
      {name}
    </span>
  );
}
