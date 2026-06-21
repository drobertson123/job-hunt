"use client";

import { useCallback, useEffect, useState } from "react";
import { Attention, AttentionItem, completeAction, fetchAttention } from "@/lib/api";
import FetchError from "@/app/components/FetchError";

const GROUPS: { kind: string; label: string }[] = [
  { kind: "overdue_followup", label: "Overdue follow-ups" },
  { kind: "overdue_action", label: "Overdue actions" },
  { kind: "stale_opportunity", label: "Stale opportunities" },
  { kind: "untriaged_opportunity", label: "Untriaged opportunities" },
];

function sevColor(severity: string): string {
  if (severity === "high") return "bg-red-500";
  if (severity === "medium") return "bg-amber-500";
  return "bg-slate-400";
}

function itemDetail(item: AttentionItem): string | null {
  if (item.kind === "overdue_followup" && item.due_at) {
    return `due ${new Date(item.due_at).toLocaleDateString()}`;
  }
  if (item.kind === "overdue_action" && item.due_at) {
    return `due ${new Date(item.due_at).toLocaleDateString()}`;
  }
  if (item.kind === "stale_opportunity") {
    const when = item.last_activity_at
      ? ` · last activity ${new Date(item.last_activity_at).toLocaleDateString()}`
      : "";
    return `${item.stage ?? ""}${when}`;
  }
  if (item.kind === "untriaged_opportunity") {
    return item.stage ?? null;
  }
  return null;
}

function Row({
  item,
  onOpen,
  onComplete,
}: {
  item: AttentionItem;
  onOpen: (id: string) => void;
  onComplete: () => void;
}) {
  const clickable = item.opportunity_id != null;
  const detail = itemDetail(item);
  return (
    <div
      onClick={clickable ? () => onOpen(item.opportunity_id as string) : undefined}
      className={`flex items-start gap-2 rounded border border-slate-200 p-2 text-sm ${
        clickable ? "cursor-pointer hover:bg-slate-50" : ""
      }`}
    >
      <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${sevColor(item.severity)}`} />
      <div className="flex flex-col">
        <span className="font-medium">{item.title}</span>
        <span className="text-xs text-slate-500">{item.reason}</span>
        {detail && <span className="text-xs text-slate-400">{detail}</span>}
      </div>
      {item.kind === "overdue_action" && item.action_id != null && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            completeAction(item.action_id as number).then(onComplete);
          }}
          className="ml-auto rounded bg-slate-200 px-2 py-0.5 text-xs hover:bg-slate-300"
        >
          Done
        </button>
      )}
    </div>
  );
}

export default function AttentionTab({ onOpen }: { onOpen: (oppId: string) => void }) {
  const [data, setData] = useState<Attention | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    fetchAttention()
      .then((d) => { setError(false); setData(d); })
      .catch(() => { setError(true); setData(null); });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <FetchError onRetry={load} />;
  if (!data) {
    return <p className="p-4 text-sm text-slate-400">Loading…</p>;
  }
  if (data.counts.total === 0) {
    return <p className="p-4 text-sm text-slate-400">Nothing needs attention 🎉</p>;
  }

  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="rounded bg-red-100 px-2 py-0.5 text-red-700">
          Follow-ups {data.counts.overdue_followups}
        </span>
        <span className="rounded bg-red-100 px-2 py-0.5 text-red-700">
          Overdue {data.counts.overdue_actions}
        </span>
        <span className="rounded bg-amber-100 px-2 py-0.5 text-amber-700">
          Stale {data.counts.stale_opportunities}
        </span>
        <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600">
          Untriaged {data.counts.untriaged_opportunities}
        </span>
        <span className="rounded bg-accent px-2 py-0.5 text-white">
          Total {data.counts.total}
        </span>
      </div>

      {GROUPS.map(({ kind, label }) => {
        const rows = data.items.filter((i) => i.kind === kind);
        if (rows.length === 0) return null;
        return (
          <div key={kind} className="flex flex-col gap-1">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {label} ({rows.length})
            </h3>
            {rows.map((item, i) => (
              <Row
                key={item.action_id ?? item.opportunity_id ?? `${kind}-${i}`}
                item={item}
                onOpen={onOpen}
                onComplete={load}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}
