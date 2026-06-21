"use client";

import { useCallback, useState } from "react";
import {
  Artifact,
  GroundingReport,
  approveArtifact,
  exportArtifact,
  getGrounding,
  runGrounding,
} from "@/lib/api";
import MarkdownView from "./MarkdownView";

// Mirror of grounding_service.py GENERATIVE_KINDS — a Task-4 check asserts they match.
const GENERATIVE_KINDS = ["cv", "cover_letter", "pitch", "outreach"] as const;
const isGenerative = (kind: string) =>
  (GENERATIVE_KINDS as readonly string[]).includes(kind);
const canExport = (a: Artifact) =>
  !isGenerative(a.kind) || a.review_status === "approved";

const BADGE: Record<Artifact["review_status"], string> = {
  draft: "bg-slate-200 text-slate-700",
  needs_review: "bg-amber-100 text-amber-800",
  approved: "bg-emerald-100 text-emerald-800",
};

export default function ArtifactCard({
  artifact,
  onChanged,
}: {
  artifact: Artifact;
  onChanged: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [report, setReport] = useState<GroundingReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generative = isGenerative(artifact.kind);
  const exportable = canExport(artifact);

  const toggle = useCallback(async () => {
    const next = !expanded;
    setExpanded(next);
    // Lazy-load any cached report the first time the card opens.
    if (next && report === null) {
      try {
        setReport(await getGrounding(artifact.id));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    }
  }, [expanded, report, artifact.id]);

  const check = useCallback(async () => {
    setBusy(true);
    try {
      setReport(await runGrounding(artifact.id));
      setError(null);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [artifact.id, onChanged]);

  const approve = useCallback(async () => {
    setBusy(true);
    try {
      await approveArtifact(artifact.id);
      setError(null);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [artifact.id, onChanged]);

  const doExport = useCallback(
    async (format: "docx" | "pdf") => {
      try {
        const r = await exportArtifact(artifact.id, format);
        window.location.assign(r.download_url);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [artifact.id],
  );

  // Annotated body only when a fresh (non-stale) report exists; else raw body.
  const bodyText =
    report && !report.stale ? report.annotated_body : artifact.body;

  return (
    <article className="rounded border bg-slate-50 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">{artifact.title}</h3>
        <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
          {artifact.kind} v{artifact.version}
        </span>
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${BADGE[artifact.review_status]}`}
        >
          {artifact.review_status.replace("_", " ")}
        </span>
        <button
          className="rounded border px-1.5 py-0.5 text-[10px] font-medium text-slate-600 hover:bg-slate-200"
          onClick={toggle}
        >
          {expanded ? "▾ Review" : "▸ Review"}
        </button>
        {(["docx", "pdf"] as const).map((fmt) =>
          exportable ? (
            <button
              key={fmt}
              className="rounded border px-1.5 py-0.5 text-[10px] font-medium text-slate-600 hover:bg-slate-200"
              onClick={() => doExport(fmt)}
            >
              {fmt}
            </button>
          ) : (
            <button
              key={fmt}
              className="cursor-not-allowed rounded border px-1.5 py-0.5 text-[10px] font-medium text-slate-300"
              disabled
              title="Approve this artifact to export"
            >
              {fmt}
            </button>
          ),
        )}
      </div>

      {artifact.provenance && (
        <p className="mt-0.5 text-[11px] text-slate-400">{artifact.provenance}</p>
      )}

      {!expanded && (
        <p className="mt-1 max-h-40 overflow-hidden whitespace-pre-wrap text-sm text-slate-700">
          {artifact.body}
        </p>
      )}

      {expanded && (
        <div className="mt-2 space-y-2">
          {error && (
            <div className="flex items-start justify-between gap-2 rounded bg-amber-100 px-3 py-2 text-sm text-amber-800">
              <span className="whitespace-pre-wrap">{error}</span>
              <button aria-label="dismiss" className="font-bold" onClick={() => setError(null)}>
                ×
              </button>
            </div>
          )}

          <div className="max-h-96 overflow-y-auto rounded border bg-white p-3">
            <MarkdownView text={bodyText} />
          </div>

          {generative && (
            <div className="space-y-2">
              <p className="text-xs text-slate-500">
                {report
                  ? `${report.unsupported_count} of ${report.checked_count} claims unsupported · threshold ${report.threshold}`
                  : "No grounding check yet."}
              </p>
              {report?.stale && (
                <p className="text-xs text-amber-700">
                  Document changed since the last check — re-check before approving.
                </p>
              )}
              <div className="flex gap-2">
                <button
                  className="rounded bg-slate-200 px-2 py-1 text-xs font-medium text-slate-800 hover:bg-slate-300 disabled:opacity-40"
                  onClick={check}
                  disabled={busy}
                >
                  {busy ? "Checking…" : report ? "Re-check" : "Check grounding"}
                </button>
                {artifact.review_status !== "approved" && (
                  <button
                    className="rounded bg-slate-900 px-2 py-1 text-xs font-medium text-white disabled:opacity-40"
                    onClick={approve}
                    disabled={busy || artifact.review_status !== "needs_review"}
                    title={
                      artifact.review_status === "needs_review"
                        ? "Approve for export"
                        : "Run a grounding check first"
                    }
                  >
                    Approve
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </article>
  );
}
