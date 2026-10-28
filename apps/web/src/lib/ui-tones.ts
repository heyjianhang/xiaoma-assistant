import type { CSSProperties } from "react";

export type UiTone = "info" | "warning" | "danger" | "success";
const accents: Record<UiTone, string> = {
  info: "var(--info, #2563eb)",
  warning: "var(--warning, #a16207)",
  danger: "var(--destructive)",
  success: "var(--success, #15803d)",
};
/** Mix with the current theme surface rather than imposing a light background. */
export function toneStyle(tone: UiTone, surface: "card" | "badge" | "control" | "alert"): CSSProperties {
  const accent = accents[tone];
  const border = `color-mix(in srgb, ${accent} 24%, var(--border))`;
  const tint = `color-mix(in srgb, ${accent} ${surface === "badge" || surface === "control" ? 9 : 4}%, var(--card))`;
  if (surface === "card") return { boxShadow: `inset 0 0 0 1px ${border}`, backgroundImage: `linear-gradient(to bottom, ${tint}, var(--card) 120px)` };
  return { color: accent, borderColor: border, backgroundColor: tint };
}
