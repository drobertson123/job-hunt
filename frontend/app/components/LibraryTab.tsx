"use client";

import { useCallback, useEffect, useState } from "react";
import { ContentBlock, deleteContentBlock, fetchContentBlocks } from "@/lib/api";
import FetchError from "./FetchError";

const KIND_LABELS: Record<string, string> = {
  headline: "Headlines",
  summary: "Summaries",
  bullet: "Bullets",
  other: "Other",
};
const KIND_ORDER = ["headline", "summary", "bullet", "other"];

export default function LibraryTab() {
  const [blocks, setBlocks] = useState<ContentBlock[]>([]);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    fetchContentBlocks()
      .then((b) => {
        setBlocks(b);
        setError(false);
      })
      .catch(() => {
        setBlocks([]);
        setError(true);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <FetchError onRetry={load} />;

  if (blocks.length === 0) {
    return (
      <div className="min-h-0 flex-1 overflow-y-auto p-4 text-sm text-ink-muted">
        <p>No content blocks yet.</p>
        <p className="mt-1 text-xs text-ink-subtle">
          Run the <span className="font-medium text-ink">content-library</span> capability in the
          chat to synthesize reusable headlines, summaries, and achievement bullets from your corpus.
        </p>
      </div>
    );
  }

  const byKind: Record<string, ContentBlock[]> = {};
  for (const b of blocks) {
    (byKind[b.kind] ??= []).push(b);
  }

  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 text-sm">
      {KIND_ORDER.filter((k) => byKind[k]?.length).map((kind) => (
        <section key={kind}>
          <h2 className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-subtle">
            {KIND_LABELS[kind] ?? kind}
          </h2>
          <div className="space-y-1.5">
            {byKind[kind].map((b) => (
              <div
                key={b.id}
                className="flex items-start gap-2 rounded border border-line bg-surface p-2"
              >
                <span className="flex-1 leading-snug">{b.text}</span>
                {b.audience && (
                  <span className="shrink-0 rounded bg-surface-sunk px-1.5 py-0.5 text-[10.5px] text-ink-muted">
                    {b.audience}
                  </span>
                )}
                <button
                  onClick={() => deleteContentBlock(b.id).then(load)}
                  className="shrink-0 rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600 hover:bg-red-50 hover:text-red-700"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
