"use client";

import { useCallback, useEffect, useState } from "react";
import { Briefing, fetchBriefing, synthesizeBriefing } from "@/lib/api";
import FetchError from "./FetchError";

export default function BriefingTab({ opportunityId }: { opportunityId: string }) {
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    if (!opportunityId) {
      setBriefing(null);
      return;
    }
    fetchBriefing(opportunityId)
      .then((b) => {
        setBriefing(b);
        setError(false);
      })
      .catch(() => {
        setBriefing(null);
        setError(true);
      });
  }, [opportunityId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!opportunityId) {
    return (
      <p className="p-4 text-sm text-gray-500">
        Select an opportunity above to see or generate its briefing.
      </p>
    );
  }

  if (error) return <FetchError onRetry={load} />;

  const synth = async () => {
    setBusy(true);
    try {
      setBriefing(await synthesizeBriefing(opportunityId));
    } catch {
      // leave existing briefing in place on failure
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 p-2">
      <button
        onClick={synth}
        disabled={busy}
        className="self-start rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        {busy ? "Synthesizing…" : briefing ? "Re-synthesize briefing" : "Synthesize briefing"}
      </button>

      {!briefing && (
        <p className="text-sm text-gray-500">No briefing yet.</p>
      )}

      {briefing && (
        <div className="flex flex-col gap-2 text-sm">
          {briefing.summary && <p className="text-gray-800">{briefing.summary}</p>}
          {briefing.facts.map((f, i) => (
            <div key={i} className="rounded border border-gray-200 p-2">
              <div className="font-medium">{f.question}</div>
              <div>{f.answer}</div>
              <div className="text-xs text-gray-500">
                {f.confidence != null && `confidence ${f.confidence.toFixed(2)}`}
                {f.source && ` · source: ${f.source}`}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
