"use client";

import type { ReactNode } from "react";

type Item = { key: string; label: string; icon: ReactNode };

const I = (d: string, sw = 1.7) => (
  <svg width="20" height="20" viewBox="0 0 21 21" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round">{<path d={d} />}</svg>
);

const ITEMS: Item[] = [
  { key: "board", label: "Board", icon: (<svg width="20" height="20" viewBox="0 0 21 21" fill="none" stroke="currentColor" strokeWidth={1.7}><rect x="2.5" y="3" width="4.2" height="15" rx="1.4"/><rect x="8.4" y="3" width="4.2" height="10" rx="1.4"/><rect x="14.3" y="3" width="4.2" height="13" rx="1.4"/></svg>) },
  { key: "weekly", label: "This week", icon: I("M3 6h7M14 6h4M3 15h4M11 15h7") },
  { key: "metrics", label: "Metrics", icon: I("M3 17.5h15.5 M5.5 17.5V11 M10.5 17.5V6.5 M15.5 17.5V9") },
  { key: "attention", label: "Attention", icon: I("M10.5 2.5L2 17h17z M10.5 8v4 M10.5 14.5v.1") },
  { key: "applications", label: "Applications", icon: I("M5 3h6l5 5v10H5z M11 3v5h5 M8 11h5M8 14h5") },
  { key: "actions", label: "Actions", icon: I("M3.5 6l2 2 3.5-4 M3.5 13l2 2 3.5-4 M12 6.5h6 M12 13.5h6") },
  { key: "briefing", label: "Briefing", icon: I("M3.5 6h14v11H3.5z M3.5 6V4.5h6V6 M7 10h7M7 13h5") },
  { key: "interviews", label: "Interviews", icon: I("M4 4h13v13H4z M4 8h13 M8 2v3 M13 2v3") },
  { key: "companies", label: "Companies", icon: I("M3 3.5h9v14H3z M12 8h5.5v9.5H12 M5.5 7h1M9 7h1M5.5 10h1M9 10h1") },
  { key: "contacts", label: "Contacts", icon: I("M8 7.5a3 3 0 100-6 3 3 0 000 6z M2.5 17c0-3 2.5-5 5.5-5s5.5 2 5.5 5 M15 5.2a2.8 2.8 0 010 5.2") },
  { key: "sources", label: "Sources", icon: I("M10.5 16a5.5 5.5 0 100-11 5.5 5.5 0 000 11z M10.5 10.5v.1 M10.5 4v1.5M10.5 15.5V17M4 10.5H2.5M18.5 10.5H17") },
  { key: "automations", label: "Automations", icon: I("M3 6h7M14 6h4M3 15h4M11 15h7") },
  { key: "library", label: "Library", icon: I("M5 3h11v15H5z M5 3a1.5 1.5 0 000 3h11 M9 7h4") },
  { key: "documents", label: "Documents", icon: I("M5 3h6l5 5v10H5z M11 3v5h5") },
  { key: "profile", label: "Profile", icon: I("M10.5 10.5a3.2 3.2 0 100-6.4 3.2 3.2 0 000 6.4z M4 18c0-3.4 2.9-5.5 6.5-5.5S17 14.6 17 18") },
  { key: "workspace", label: "Workspace", icon: I("M3 5.5h5l1.5 2H18v9.5H3z") },
];

export default function IconRail({
  active,
  onSelect,
  initials = "DR",
}: {
  active: string;
  onSelect: (k: string) => void;
  initials?: string;
}) {
  const items = ITEMS.filter((it, i, a) => a.findIndex((x) => x.key === it.key) === i);
  return (
    <nav className="flex w-[76px] flex-none flex-col items-center gap-2.5 border-r border-line bg-surface py-4">
      <div className="mb-3 flex h-[42px] w-[42px] items-center justify-center rounded-md bg-accent shadow-accent">
        <svg width="22" height="22" viewBox="0 0 22 22" fill="none"><circle cx="6" cy="6" r="2.6" fill="#fff"/><circle cx="16" cy="11" r="2.6" fill="#fff"/><circle cx="7" cy="16" r="2.6" fill="#fff"/><path d="M6 6 L16 11 M16 11 L7 16" stroke="#fff" strokeWidth="1.4" strokeLinecap="round" opacity=".75"/></svg>
      </div>
      <div className="flex w-full flex-1 flex-col items-center gap-1.5 overflow-y-auto py-0.5">
        {items.map((it) => {
          const on = active === it.key;
          return (
            <button
              key={it.key}
              title={it.label}
              onClick={() => onSelect(it.key)}
              className={`flex h-11 w-11 flex-none items-center justify-center rounded-md transition ${
                on ? "bg-accent-tint text-accent" : "text-ink-muted hover:bg-surface-sunk"
              }`}
            >
              {it.icon}
            </button>
          );
        })}
      </div>
      <div className="mt-auto flex flex-col items-center gap-3">
        <span className="h-2 w-2 animate-pulse rounded-full bg-ok" title="Automation active" />
        <span className="flex h-[38px] w-[38px] items-center justify-center rounded-full bg-panel text-[13px] font-semibold text-white">
          {initials}
        </span>
      </div>
    </nav>
  );
}
