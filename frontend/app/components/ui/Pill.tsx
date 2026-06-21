import type { ReactNode } from "react";

type Tone = "neutral" | "accent" | "ok" | "override" | "warn" | "error" | "stale";

const TONE: Record<Tone, string> = {
  neutral: "bg-surface-sunk text-ink-muted",
  accent: "bg-accent-soft text-accent-ink",
  ok: "bg-ok-soft text-ok",
  override: "bg-override-soft text-override",
  warn: "bg-warn-soft text-warn",
  error: "bg-error-soft text-error",
  stale: "bg-stale-soft text-stale",
};
const SOLID: Record<Tone, string> = {
  neutral: "bg-ink-muted text-white",
  accent: "bg-accent text-white",
  ok: "bg-ok text-white",
  override: "bg-override text-white",
  warn: "bg-warn text-white",
  error: "bg-error text-white",
  stale: "bg-stale text-white",
};

export default function Pill({
  tone = "neutral",
  size = "md",
  mono = false,
  solid = false,
  children,
}: {
  tone?: Tone;
  size?: "sm" | "md";
  mono?: boolean;
  solid?: boolean;
  children: ReactNode;
}) {
  const pad = size === "sm" ? "px-1.5 py-px text-[10px]" : "px-2 py-0.5 text-[11px]";
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-sm font-semibold leading-tight ${
        mono ? "font-mono" : ""
      } ${pad} ${solid ? SOLID[tone] : TONE[tone]}`}
    >
      {children}
    </span>
  );
}
