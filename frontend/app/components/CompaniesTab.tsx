"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Company,
  Opportunity,
  backfillCompanies,
  fetchCompanies,
  fetchOpportunities,
} from "@/lib/api";
import FetchError from "./FetchError";

export default function CompaniesTab({ onOpen }: { onOpen: (oppId: string) => void }) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    Promise.all([fetchCompanies(), fetchOpportunities()])
      .then(([c, o]) => {
        setCompanies(c);
        setOpps(o);
        setError(false);
      })
      .catch(() => {
        setCompanies([]);
        setOpps([]);
        setError(true);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runBackfill = async () => {
    setBusy(true);
    try {
      await backfillCompanies();
      load();
    } finally {
      setBusy(false);
    }
  };

  if (error) return <FetchError onRetry={load} />;

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-5">
      {/* Header */}
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-[22px] font-bold tracking-tight text-ink">Companies</h2>
          <p className="text-[13.5px] text-ink-muted">
            {companies.length} companies · {opps.length} roles tracked — profiles auto-enriched.
          </p>
        </div>
        <button
          onClick={runBackfill}
          disabled={busy}
          className="flex-none rounded-md bg-accent px-3.5 py-2 text-[13px] font-semibold text-white hover:bg-accent-ink disabled:opacity-50"
        >
          {busy ? "Backfilling…" : "Backfill from opportunities"}
        </button>
      </div>

      {/* Empty state */}
      {companies.length === 0 ? (
        <p className="text-ink-subtle">No companies yet. Run backfill or let the agent add them.</p>
      ) : (
        <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fill,minmax(330px,1fr))]">
          {companies.map((c) => {
            // Match the backend's case-insensitive, trimmed name dedup so opps
            // aren't silently dropped when org casing/whitespace differs.
            const linked = opps.filter(
              (o) => o.organization?.trim().toLowerCase() === c.name.trim().toLowerCase(),
            );
            return (
              <div key={c.id} className="rounded-xl border border-line bg-surface p-4 transition hover:border-line-strong hover:shadow-pop">
                <div className="flex items-start gap-3">
                  <div className="flex h-10 w-10 flex-none items-center justify-center rounded-md bg-accent-tint text-[13px] font-bold text-accent">
                    {c.name.slice(0, 2).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[14.5px] font-semibold text-ink">{c.name}</div>
                    <div className="truncate text-[12.5px] text-ink-muted">
                      {[c.industry, c.size, c.hq_location].filter(Boolean).join(" · ") || "—"}
                    </div>
                  </div>
                  {c.ats_vendor && (
                    <span className="flex-none rounded-xs bg-surface-sunk px-1.5 py-0.5 font-mono text-[10px] text-ink-subtle">{c.ats_vendor}</span>
                  )}
                </div>
                {c.summary && <p className="mt-2.5 line-clamp-2 text-[12.5px] leading-snug text-ink-body">{c.summary}</p>}
                <div className="mt-3 border-t border-line-soft pt-2.5">
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-subtle">
                    {linked.length} role{linked.length === 1 ? "" : "s"}
                  </div>
                  <div className="mt-1.5 flex flex-col gap-1">
                    {linked.slice(0, 4).map((o) => (
                      <button key={o.id} onClick={() => onOpen(o.id)} className="truncate text-left text-[12.5px] text-accent hover:underline">
                        {o.title}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
