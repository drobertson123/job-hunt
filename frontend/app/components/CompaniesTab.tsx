"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Company,
  Opportunity,
  backfillCompanies,
  fetchCompanies,
  fetchOpportunities,
} from "@/lib/api";

export default function CompaniesTab({ onOpen }: { onOpen: (oppId: string) => void }) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    fetchCompanies().then(setCompanies).catch(() => setCompanies([]));
    fetchOpportunities().then(setOpps).catch(() => setOpps([]));
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

  return (
    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 text-sm">
      <button
        onClick={runBackfill}
        disabled={busy}
        className="self-start rounded bg-slate-900 px-3 py-1.5 text-xs text-white disabled:opacity-50"
      >
        {busy ? "Backfilling…" : "Backfill from opportunities"}
      </button>

      {companies.length === 0 ? (
        <p className="text-slate-400">No companies yet. Run backfill or let the agent add them.</p>
      ) : (
        companies.map((c) => {
          // Match the backend's case-insensitive, trimmed name dedup so opps
          // aren't silently dropped when org casing/whitespace differs.
          const linked = opps.filter(
            (o) => o.organization?.trim().toLowerCase() === c.name.trim().toLowerCase(),
          );
          return (
            <div key={c.id} className="rounded border border-slate-200 p-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{c.name}</span>
                {c.industry && <span className="text-xs text-slate-500">{c.industry}</span>}
                {c.size && c.size !== "unknown" && (
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{c.size}</span>
                )}
                {c.ats_vendor && (
                  <span className="text-xs text-slate-400">ATS: {c.ats_vendor}</span>
                )}
              </div>
              {linked.map((o) => (
                <div
                  key={o.id}
                  onClick={() => onOpen(o.id)}
                  className="mt-1 cursor-pointer text-xs text-blue-600 hover:underline"
                >
                  {o.title}
                </div>
              ))}
            </div>
          );
        })
      )}
    </div>
  );
}
