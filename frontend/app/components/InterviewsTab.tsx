"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Interview,
  Opportunity,
  createInterview,
  deleteInterview,
  fetchInterviews,
  fetchOpportunities,
} from "@/lib/api";
import FetchError from "./FetchError";

const KINDS = ["phone", "video", "onsite", "technical", "behavioral", "final", "other"];

export default function InterviewsTab({ onOpen }: { onOpen: (oppId: string) => void }) {
  const [items, setItems] = useState<Interview[]>([]);
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("phone");
  const [startsAt, setStartsAt] = useState("");
  const [location, setLocation] = useState("");
  const [oppId, setOppId] = useState("");
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    fetchInterviews(true)
      .then((x) => {
        setItems(x);
        setError(false);
      })
      .catch(() => {
        setItems([]);
        setError(true);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    fetchOpportunities().then(setOpps).catch(() => setOpps([]));
  }, []);

  const submit = async () => {
    if (!title.trim() || !startsAt) return;
    await createInterview({
      title: title.trim(),
      starts_at: startsAt,
      kind,
      location: location.trim(),
      opportunity_id: oppId || null,
    });
    setTitle("");
    setStartsAt("");
    setLocation("");
    setOppId("");
    setKind("phone");
    load();
  };

  const titleFor = (id: string | null) =>
    id ? opps.find((o) => o.id === id)?.title ?? id : null;

  if (error) return <FetchError onRetry={load} />;

  return (
    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 text-sm">
      <div className="flex flex-wrap items-center gap-2 rounded border border-slate-200 p-2">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Interview title…"
          className="flex-1 rounded border px-2 py-1 text-sm"
        />
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          className="rounded border px-1 py-1 text-xs"
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <input
          type="datetime-local"
          value={startsAt}
          onChange={(e) => setStartsAt(e.target.value)}
          className="rounded border px-1 py-1 text-xs"
        />
        <input
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          placeholder="Location / link"
          className="rounded border px-2 py-1 text-xs"
        />
        <select
          value={oppId}
          onChange={(e) => setOppId(e.target.value)}
          className="rounded border px-1 py-1 text-xs"
        >
          <option value="">— no opportunity —</option>
          {opps.map((o) => (
            <option key={o.id} value={o.id}>
              {o.title}
            </option>
          ))}
        </select>
        <button
          onClick={submit}
          disabled={!title.trim() || !startsAt}
          className="rounded bg-slate-900 px-3 py-1 text-xs text-white disabled:opacity-50"
        >
          Add
        </button>
      </div>

      <div className="flex justify-end">
        <a
          href="/api/interviews/calendar.ics"
          className="rounded bg-slate-100 px-2 py-1 text-xs text-slate-700 hover:bg-slate-200"
        >
          Download all (.ics)
        </a>
      </div>

      {items.length === 0 ? (
        <p className="text-slate-400">No upcoming interviews.</p>
      ) : (
        items.map((iv) => {
          const t = titleFor(iv.opportunity_id);
          return (
            <div
              key={iv.id}
              className="flex items-center gap-2 rounded border border-slate-200 p-2"
            >
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs uppercase text-slate-600">
                {iv.kind}
              </span>
              <span className="flex-1">{iv.title}</span>
              {iv.location && (
                <span className="text-xs text-slate-500">{iv.location}</span>
              )}
              {t && (
                <span
                  onClick={() => onOpen(iv.opportunity_id as string)}
                  className="cursor-pointer text-xs text-blue-600 hover:underline"
                >
                  {t}
                </span>
              )}
              <span className="text-xs text-slate-500">
                {new Date(iv.starts_at).toLocaleString()}
              </span>
              <a
                href={`/api/interviews/${iv.id}.ics`}
                className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700 hover:bg-slate-200"
              >
                Add to calendar
              </a>
              <button
                onClick={() => deleteInterview(iv.id).then(load)}
                className="rounded bg-slate-200 px-2 py-0.5 text-xs hover:bg-slate-300"
              >
                Remove
              </button>
            </div>
          );
        })
      )}
    </div>
  );
}
