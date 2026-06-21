"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Action,
  Opportunity,
  completeAction,
  createAction,
  fetchActions,
  fetchOpportunities,
  reopenAction,
  snoozeAction,
} from "@/lib/api";
import FetchError from "./FetchError";

type Filter = "open" | "done" | "all";
const KINDS = ["followup", "apply", "research", "prep", "outreach", "decision", "other"];

export default function ActionsTab({ onOpen }: { onOpen: (oppId: string) => void }) {
  const [actions, setActions] = useState<Action[]>([]);
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [filter, setFilter] = useState<Filter>("open");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("other");
  const [dueAt, setDueAt] = useState("");
  const [oppId, setOppId] = useState("");
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    fetchActions(filter === "all" ? undefined : filter)
      .then((a) => {
        setActions(a);
        setError(false);
      })
      .catch(() => {
        setActions([]);
        setError(true);
      });
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    fetchOpportunities().then(setOpps).catch(() => setOpps([]));
  }, []);

  const submit = async () => {
    if (!title.trim()) return;
    await createAction({
      title: title.trim(),
      kind,
      due_at: dueAt || null,
      opportunity_id: oppId || null,
    });
    setTitle("");
    setDueAt("");
    setOppId("");
    setKind("other");
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
          placeholder="New action…"
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
          type="date"
          value={dueAt}
          onChange={(e) => setDueAt(e.target.value)}
          className="rounded border px-1 py-1 text-xs"
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
          disabled={!title.trim()}
          className="rounded bg-slate-900 px-3 py-1 text-xs text-white disabled:opacity-50"
        >
          Add
        </button>
      </div>

      <div className="flex gap-1">
        {(["open", "done", "all"] as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded px-2 py-1 text-xs capitalize ${
              filter === f ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {actions.length === 0 ? (
        <p className="text-slate-400">No actions.</p>
      ) : (
        actions.map((a) => {
          const t = titleFor(a.opportunity_id);
          const past =
            a.due_at && a.status === "open" && new Date(a.due_at) < new Date();
          return (
            <div
              key={a.id}
              className="flex items-center gap-2 rounded border border-slate-200 p-2"
            >
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs uppercase text-slate-600">
                {a.kind}
              </span>
              <span className="flex-1">{a.title}</span>
              {t && (
                <span
                  onClick={() => onOpen(a.opportunity_id as string)}
                  className="cursor-pointer text-xs text-blue-600 hover:underline"
                >
                  {t}
                </span>
              )}
              {a.due_at && (
                <span className={`text-xs ${past ? "text-red-600" : "text-slate-500"}`}>
                  {new Date(a.due_at).toLocaleDateString()}
                </span>
              )}
              {a.status === "open" ? (
                <>
                  <button
                    onClick={() => completeAction(a.id).then(load)}
                    className="rounded bg-slate-200 px-2 py-0.5 text-xs hover:bg-slate-300"
                  >
                    Done
                  </button>
                  <button
                    onClick={() => snoozeAction(a.id).then(load)}
                    className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-200"
                  >
                    Snooze
                  </button>
                </>
              ) : (
                <>
                  <span className="text-xs text-slate-400">{a.status}</span>
                  <button
                    onClick={() => reopenAction(a.id).then(load)}
                    className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-200"
                  >
                    Reopen
                  </button>
                </>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
