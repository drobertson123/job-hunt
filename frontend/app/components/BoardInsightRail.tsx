"use client";

import { useEffect, useState } from "react";
import {
  Attention,
  RunSummary,
  Application,
  Opportunity,
  fetchAttention,
  fetchRuns,
  fetchApplications,
  fetchOpportunities,
} from "@/lib/api";

const ACTIVE = new Set(["active", "in_dialogue"]);

function timeAgo(iso: string): string {
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return `${Math.floor(d / 86400)}d ago`;
}

export default function BoardInsightRail({ onOpen }: { onOpen: (oppId: string) => void }) {
  const [att, setAtt] = useState<Attention | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [apps, setApps] = useState<Application[]>([]);
  const [opps, setOpps] = useState<Opportunity[]>([]);

  useEffect(() => {
    fetchAttention().then(setAtt).catch(() => setAtt(null));
    fetchRuns(12).then(setRuns).catch(() => setRuns([]));
    fetchApplications().then(setApps).catch(() => setApps([]));
    fetchOpportunities().then(setOpps).catch(() => setOpps([]));
  }, []);

  const decisions = (att?.items ?? []).filter(
    (i) => i.severity === "high" || i.kind === "untriaged_message"
  );
  const activeCount = opps.filter((o) => ACTIVE.has(o.stage)).length;

  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto bg-surface-alt p-5">
      {/* decisions */}
      <div>
        <div className="mb-3 flex items-center gap-2">
          <span className="text-[12px] font-bold uppercase tracking-wide text-ink-muted">Needs your decision</span>
          {decisions.length > 0 && (
            <span className="rounded-full bg-error px-1.5 text-[11px] font-bold text-white">{decisions.length}</span>
          )}
        </div>
        <div className="flex flex-col gap-2.5">
          {decisions.length === 0 ? (
            <div className="rounded-lg border border-ok-soft bg-ok-soft px-4 py-3 text-center text-[13px] font-semibold text-ok-deep">
              All caught up — automation has it from here.
            </div>
          ) : (
            decisions.slice(0, 6).map((d, i) => (
              <button
                key={i}
                onClick={() => d.opportunity_id && onOpen(d.opportunity_id)}
                className="rounded-xl border border-line bg-surface p-3 text-left transition hover:border-line-strong"
              >
                <div className="text-[13.5px] font-semibold leading-snug text-ink">{d.title}</div>
                <div className="mt-0.5 text-[12px] text-ink-muted">{d.reason}</div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* automation activity */}
      <div>
        <div className="mb-3 text-[12px] font-bold uppercase tracking-wide text-ink-muted">Automation activity</div>
        <div className="flex flex-col gap-3.5">
          {runs.length === 0 ? (
            <div className="text-[12.5px] text-ink-subtle">No recent runs.</div>
          ) : (
            runs.slice(0, 8).map((r) => (
              <div key={r.id} className="flex gap-2.5">
                <span className={`mt-1.5 h-2 w-2 flex-none rounded-full ${r.status === "completed" ? "bg-ok" : r.status === "failed" ? "bg-error" : "bg-accent"}`} />
                <div>
                  <div className="text-[12.5px] leading-snug text-ink-body">{r.prompt || "(agent run)"}</div>
                  <div className="font-mono text-[10px] text-ink-subtle">{r.status} · {timeAgo(r.created_at)}</div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* mini metrics (dark) */}
      <div className="rounded-xl bg-panel p-4 text-white">
        <div className="mb-3 text-[12px] font-bold uppercase tracking-wide text-white/60">Pipeline</div>
        <div className="flex gap-2.5">
          <div className="flex-1"><div className="text-[24px] font-bold leading-none">{apps.length}</div><div className="mt-1 text-[11px] text-white/55">Applied</div></div>
          <div className="flex-1"><div className="text-[24px] font-bold leading-none text-ok-mint">{activeCount}</div><div className="mt-1 text-[11px] text-white/55">Active</div></div>
          <div className="flex-1"><div className="text-[24px] font-bold leading-none">{decisions.length}</div><div className="mt-1 text-[11px] text-white/55">Decisions</div></div>
        </div>
      </div>
    </div>
  );
}
