"use client";

import Pill from "./ui/Pill";

type Tone = "neutral" | "warn";
type Item = { key: string; label: string; tone?: Tone };

const SECTIONS: { title: string; items: Item[] }[] = [
  {
    title: "Pipeline",
    items: [
      { key: "board", label: "Board" },
      { key: "detail", label: "Detail" },
      { key: "attention", label: "Attention", tone: "warn" },
      { key: "weekly", label: "This week" },
    ],
  },
  {
    title: "Track",
    items: [
      { key: "applications", label: "Applications" },
      { key: "interviews", label: "Interviews" },
      { key: "actions", label: "Actions" },
    ],
  },
  {
    title: "Research",
    items: [
      { key: "companies", label: "Companies" },
      { key: "sources", label: "Sources" },
      { key: "briefing", label: "Briefing" },
    ],
  },
  {
    title: "You",
    items: [
      { key: "workspace", label: "Workspace" },
      { key: "profile", label: "Profile" },
      { key: "library", label: "Library" },
    ],
  },
];

export default function LeftNav({
  active,
  onSelect,
  counts,
}: {
  active: string;
  onSelect: (k: string) => void;
  counts: Record<string, number>;
}) {
  return (
    <nav className="flex w-[196px] flex-shrink-0 flex-col gap-3.5 overflow-y-auto border-r border-line bg-surface py-3">
      {SECTIONS.map((sec) => (
        <div key={sec.title}>
          <div className="px-4 pb-1 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-subtle">
            {sec.title}
          </div>
          {sec.items.map((it) => {
            const on = active === it.key;
            const c = counts[it.key];
            return (
              <button
                key={it.key}
                onClick={() => onSelect(it.key)}
                className={`flex w-full items-center justify-between border-l-2 px-4 py-1.5 text-left text-[12.5px] transition ${
                  on
                    ? "border-accent bg-accent-soft font-semibold text-ink"
                    : "border-transparent font-medium text-ink-muted hover:bg-surface-sunk"
                }`}
              >
                <span>{it.label}</span>
                {typeof c === "number" && c > 0 && (
                  <Pill tone={on ? "accent" : it.tone ?? "neutral"} size="sm">
                    {c}
                  </Pill>
                )}
              </button>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
