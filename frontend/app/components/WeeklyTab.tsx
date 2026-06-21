"use client";

import { useCallback, useEffect, useState } from "react";
import {
  WeeklyReview,
  WeeklyOpp,
  createWeeklyActions,
  fetchWeeklyReview,
} from "@/lib/api";
import FetchError from "./FetchError";

export default function WeeklyTab({ onOpen }: { onOpen: (oppId: string) => void }) {
  const [data, setData] = useState<WeeklyReview | null>(null);
  const [error, setError] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(() => {
    fetchWeeklyReview()
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

  const materialize = async () => {
    const r = await createWeeklyActions();
    setMsg(`${r.created} action${r.created === 1 ? "" : "s"} created`);
    load();
  };

  if (error) return <FetchError onRetry={load} />;
  if (!data) return <p className="p-4 text-sm text-slate-400">Loading…</p>;

  const bucket = (label: string, items: WeeklyOpp[]) => (
    <div className="rounded border border-slate-200 p-2">
      <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">
        {label} ({items.length})
      </h3>
      {items.length === 0 ? (
        <p className="text-xs text-slate-400">Nothing here.</p>
      ) : (
        <ul className="space-y-1">
          {items.map((o) => (
            <li
              key={o.id}
              onClick={() => onOpen(o.id)}
              className="cursor-pointer rounded px-1.5 py-1 text-sm hover:bg-slate-50"
            >
              <span className="font-medium">{o.title}</span>
              {o.organization && (
                <span className="text-slate-500"> · {o.organization}</span>
              )}
              <span className="ml-1 text-xs text-slate-400">[{o.stage}]</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  return (
    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 text-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">This week</h2>
        <div className="flex items-center gap-2">
          {msg && <span className="text-xs text-green-700">{msg}</span>}
          <button
            onClick={materialize}
            className="rounded bg-accent px-3 py-1 text-xs text-white"
          >
            Create this week&apos;s actions
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {bucket("Identify", data.to_identify)}
        {bucket("Apply", data.to_apply)}
        {bucket("Follow up", data.to_follow_up)}
      </div>

      <div className="rounded border border-slate-200 p-2">
        <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">
          Interviews this week ({data.interviews_this_week.length})
        </h3>
        {data.interviews_this_week.length === 0 ? (
          <p className="text-xs text-slate-400">None scheduled.</p>
        ) : (
          <ul className="space-y-1">
            {data.interviews_this_week.map((iv) => (
              <li key={iv.id} className="text-sm">
                <span className="font-medium">{iv.title}</span>{" "}
                <span className="text-xs text-slate-500">
                  {new Date(iv.starts_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
