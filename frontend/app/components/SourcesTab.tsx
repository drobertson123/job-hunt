"use client";

import { useCallback, useEffect, useState } from "react";
import {
  JobSource,
  createJobSource,
  fetchJobSources,
  runJobSourceSearch,
  updateJobSource,
} from "@/lib/api";
import FetchError from "./FetchError";

export default function SourcesTab() {
  const [sources, setSources] = useState<JobSource[]>([]);
  const [error, setError] = useState(false);
  const [name, setName] = useState("");
  const [query, setQuery] = useState("");
  const [searchingId, setSearchingId] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchJobSources()
      .then((s) => {
        setSources(s);
        setError(false);
      })
      .catch(() => {
        setSources([]);
        setError(true);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async () => {
    if (!name.trim()) return;
    await createJobSource({ name: name.trim(), saved_query: query.trim() || null });
    setName("");
    setQuery("");
    load();
  };

  const handleQueryBlur = async (src: JobSource, value: string) => {
    if (value === (src.saved_query ?? "")) return;
    await updateJobSource(src.id, { saved_query: value.trim() || null });
    load();
  };

  const handleAutoSearchToggle = async (src: JobSource, checked: boolean) => {
    await updateJobSource(src.id, { auto_search: checked });
    load();
  };

  const handleSearchNow = async (src: JobSource) => {
    setSearchingId(src.id);
    try {
      await runJobSourceSearch(src.id);
    } finally {
      setSearchingId(null);
      load();
    }
  };

  if (error) return <FetchError onRetry={load} />;

  return (
    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 text-sm">
      {/* Add row */}
      <div className="flex flex-wrap items-center gap-2 rounded border border-slate-200 p-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Source name…"
          className="flex-1 rounded border px-2 py-1 text-sm"
        />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Saved query (optional)…"
          className="flex-1 rounded border px-2 py-1 text-sm"
        />
        <button
          onClick={submit}
          disabled={!name.trim()}
          className="rounded bg-accent px-3 py-1 text-xs text-white disabled:opacity-50"
        >
          Add
        </button>
      </div>

      {/* Source list */}
      {sources.length === 0 ? (
        <p className="text-slate-400">No job sources. Add one above.</p>
      ) : (
        sources.map((src) => (
          <div
            key={src.id}
            className="space-y-2 rounded border border-slate-200 p-3"
          >
            <div className="flex items-center gap-2">
              <span className="font-medium">{src.name}</span>
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs uppercase text-slate-600">
                {src.kind}
              </span>
              <span className="ml-auto text-xs text-slate-400">
                Last checked:{" "}
                {src.last_checked_at
                  ? new Date(src.last_checked_at).toLocaleString()
                  : "never"}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <input
                defaultValue={src.saved_query ?? ""}
                onBlur={(e) => handleQueryBlur(src, e.target.value)}
                placeholder="Saved query…"
                className="flex-1 rounded border px-2 py-1 text-xs"
              />
              <label className="flex items-center gap-1 text-xs">
                <input
                  type="checkbox"
                  checked={src.auto_search}
                  onChange={(e) => handleAutoSearchToggle(src, e.target.checked)}
                />
                Auto-search
              </label>
              <button
                onClick={() => handleSearchNow(src)}
                disabled={searchingId === src.id}
                className="rounded bg-slate-200 px-2 py-1 text-xs hover:bg-slate-300 disabled:opacity-50"
              >
                {searchingId === src.id ? "Searching…" : "Search now"}
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
