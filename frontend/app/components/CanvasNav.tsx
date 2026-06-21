"use client";

type Item = { key: string; label: string; count?: number };

export default function CanvasNav({
  active,
  onSelect,
  counts,
}: {
  active: string;
  onSelect: (t: string) => void;
  counts: Record<string, number>;
}) {
  const groups: Item[][] = [
    [
      { key: "board", label: "Board", count: counts.board },
      { key: "detail", label: "Detail" },
      { key: "attention", label: "Attention", count: counts.attention },
      { key: "weekly", label: "This week" },
    ],
    [
      { key: "applications", label: "Applications", count: counts.applications },
      { key: "interviews", label: "Interviews" },
      { key: "actions", label: "Actions", count: counts.actions },
    ],
    [
      { key: "companies", label: "Companies", count: counts.companies },
      { key: "sources", label: "Sources" },
      { key: "briefing", label: "Briefing" },
    ],
    [
      { key: "workspace", label: "Workspace", count: counts.workspace },
      { key: "profile", label: "Profile" },
    ],
  ];

  return (
    <nav className="flex flex-wrap items-center gap-1 border-b border-slate-200 bg-white px-3 py-2">
      {groups.map((items, gi) => (
        <div key={gi} className="flex flex-wrap items-center gap-1">
          {gi > 0 && (
            <span className="mx-1 hidden h-4 w-px bg-slate-200 sm:inline-block" aria-hidden />
          )}
          {items.map((it) => {
            const on = active === it.key;
            return (
              <button
                key={it.key}
                onClick={() => onSelect(it.key)}
                className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition ${
                  on
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {it.label}
                {typeof it.count === "number" && it.count > 0 && (
                  <span
                    className={`rounded-full px-1.5 text-[10px] ${
                      on ? "bg-white/25 text-white" : "bg-slate-200 text-slate-600"
                    }`}
                  >
                    {it.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
