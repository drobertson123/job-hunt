"use client";

import { useCallback, useEffect, useState } from "react";
import { Metrics, fetchMetrics } from "@/lib/api";
import FetchError from "./FetchError";

export default function MetricsTab() {
  const [data, setData] = useState<Metrics | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    fetchMetrics()
      .then((d) => {
        setData(d);
        setError(false);
      })
      .catch(() => {
        setData(null);
        setError(true);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <FetchError onRetry={load} />;
  if (!data) return <p className="p-4 text-sm text-ink-muted">Loading…</p>;

  const { kpis, funnel, volume, sources } = data;

  // Guard divide-by-zero
  const funnelBase = funnel.length > 0 && funnel[0].count > 0 ? funnel[0].count : 1;
  const maxVol = Math.max(...volume.map((v) => v.count), 1);
  const maxSource = Math.max(...sources.map((s) => s.count), 1);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-6 space-y-6">
      {/* KPI grid */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          { label: "Total applications", value: kpis.total_applications, accent: false },
          { label: "Response rate", value: `${kpis.response_rate}%`, accent: true },
          { label: "Interview rate", value: `${kpis.interview_rate}%`, accent: true },
          { label: "Active", value: kpis.active, accent: false },
        ].map(({ label, value, accent }) => (
          <div key={label} className="rounded-xl border border-line bg-surface p-4">
            <div className="text-xs text-ink-subtle uppercase tracking-wide mb-1">{label}</div>
            <div className={`text-[30px] font-bold leading-none ${accent ? "text-accent" : "text-ink"}`}>
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* Conversion funnel */}
      <div className="rounded-xl border border-line bg-surface p-5">
        <h2 className="text-sm font-semibold text-ink mb-4">Conversion funnel</h2>
        <div className="space-y-3">
          {funnel.map((row) => {
            const pct = Math.round((row.count / funnelBase) * 100);
            return (
              <div key={row.label}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm text-ink">{row.label}</span>
                  <span className="text-sm text-ink-muted">
                    {row.count}
                    {row.rate !== null ? ` · ${row.rate}%` : ""}
                  </span>
                </div>
                <div className="h-2 w-full rounded-full bg-surface-sunk overflow-hidden">
                  <div
                    className="h-2 rounded-full bg-accent"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Application volume */}
      <div className="rounded-xl border border-line bg-surface p-5">
        <h2 className="text-sm font-semibold text-ink mb-4">Application volume</h2>
        <div className="flex items-end gap-2 h-24">
          {volume.map((v, i) => {
            const heightPct = Math.round((v.count / maxVol) * 100);
            const isLast = i === volume.length - 1;
            return (
              <div key={v.week} className="flex flex-1 flex-col items-center gap-1">
                <div className="w-full flex items-end justify-center" style={{ height: "80px" }}>
                  <div
                    className={`w-full rounded-t ${isLast ? "bg-accent" : "bg-accent-tint"}`}
                    style={{ height: `${Math.max(heightPct, 4)}%` }}
                    title={`${v.week}: ${v.count}`}
                  />
                </div>
                <span className="text-[10px] text-ink-subtle truncate w-full text-center">{v.week}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Where responses come from */}
      <div className="rounded-xl border border-line bg-surface p-5">
        <h2 className="text-sm font-semibold text-ink mb-4">Where responses come from</h2>
        {sources.length === 0 ? (
          <p className="text-sm text-ink-muted">No source data yet.</p>
        ) : (
          <div className="space-y-3">
            {sources.map((s) => {
              const pct = Math.round((s.count / maxSource) * 100);
              return (
                <div key={s.source} className="flex items-center gap-3">
                  <span className="w-28 text-sm text-ink truncate capitalize">{s.source}</span>
                  <div className="flex-1 h-2 rounded-full bg-surface-sunk overflow-hidden">
                    <div
                      className="h-2 rounded-full bg-accent"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-sm text-ink-muted w-6 text-right">{s.count}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
