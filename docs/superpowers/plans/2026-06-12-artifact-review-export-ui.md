# Artifact Review & Export UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users view an artifact's grounding report, approve generative artifacts (`needs_review → approved`), and export them — fixing the dead-end where a tailored CV can't leave the app.

**Architecture:** Spec: `docs/superpowers/specs/2026-06-12-artifact-review-export-ui-design.md`. Zero backend changes (the grounding/approve/export endpoints already exist). Three frontend units: grounding/approve client functions in `frontend/lib/api.ts`; a new self-contained `ArtifactCard` component owning per-card review state and export gating; and a `page.tsx` edit that renders `<ArtifactCard/>` instead of the inline artifact markup.

**Tech Stack:** Next.js 14 static export, React client components, Tailwind. No frontend unit-test infra (repo convention) — each task is verified by the production build type-checking and compiling; the final task runs the backend suite (must stay green) and a live seam check.

**Verification convention:** `NODE_ENV=production npm --prefix frontend run build` must exit 0 ("Compiled successfully"). The backend pytest suite must stay untouched and green.

---

### Task 1: Grounding/approve API client (`frontend/lib/api.ts`)

**Files:**
- Modify: `frontend/lib/api.ts` (append after `approveArtifact`'s natural home — i.e. after the corpus block at end of file)

- [ ] **Step 1: Add types and three functions**

Append to `frontend/lib/api.ts`:

```ts
// ----- artifact grounding & approval (spec: 2026-06-12-artifact-review-export-ui) -----

export type GroundingFinding = {
  text: string;
  start: number;
  end: number;
  score: number;
  chunk_id: number | null;
  document_title: string | null;
  supported: boolean;
};

export type GroundingReport = {
  artifact_id: number;
  threshold: number;
  embedding_model: string;
  checked_count: number;
  unsupported_count: number;
  findings: GroundingFinding[];
  annotated_body: string;
  stale: boolean;
  created_at: string;
};

/** Run the embedding-similarity grounding check; also flips status to needs_review. */
export async function runGrounding(id: number): Promise<GroundingReport> {
  const res = await fetch(`/api/artifacts/${id}/grounding`, { method: "POST" });
  if (!res.ok) await throwDetail(res, `grounding failed: ${res.status}`);
  return res.json();
}

/** Cached grounding report, or null when none exists yet (the server's 404). */
export async function getGrounding(id: number): Promise<GroundingReport | null> {
  const res = await fetch(`/api/artifacts/${id}/grounding`);
  if (res.status === 404) return null;
  if (!res.ok) await throwDetail(res, `grounding fetch failed: ${res.status}`);
  return res.json();
}

/** Transition needs_review -> approved; 409 from any other status (surfaced via detail). */
export async function approveArtifact(id: number): Promise<Artifact> {
  const res = await fetch(`/api/artifacts/${id}/approve`, { method: "POST" });
  if (!res.ok) await throwDetail(res, `approve failed: ${res.status}`);
  return res.json();
}
```

`throwDetail` and the `Artifact` type already exist in this file (from earlier work) — do not redeclare them.

- [ ] **Step 2: Verify the build**

Run: `NODE_ENV=production npm --prefix frontend run build`
Expected: exit 0, "Compiled successfully".

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(frontend): grounding + approve API client functions"
```

---

### Task 2: `ArtifactCard` component

**Files:**
- Create: `frontend/app/components/ArtifactCard.tsx`

This component reproduces today's collapsed card (title, kind/version chip, status badge, provenance, truncated preview, docx/pdf buttons) and adds the Review expand. It owns the `BADGE` map and the export action (`doExport`) which currently live in `page.tsx` — they move here because export is now a card-local concern.

- [ ] **Step 1: Create the component file**

Full content of `frontend/app/components/ArtifactCard.tsx`:

```tsx
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

          <div className="max-h-96 overflow-y-auto whitespace-pre-wrap rounded border bg-white p-3 text-sm text-slate-700">
            {bodyText}
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
```

- [ ] **Step 2: Verify the build**

Run: `NODE_ENV=production npm --prefix frontend run build`
Expected: exit 0. (Component not yet referenced — this proves it type-checks/compiles.)

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/ArtifactCard.tsx
git commit -m "feat(frontend): ArtifactCard with inline grounding review + export gating"
```

---

### Task 3: Wire `ArtifactCard` into `page.tsx`

**Files:**
- Modify: `frontend/app/page.tsx` (imports; remove `BADGE` const; remove `doExport`; replace the artifact `<article>` map in the workspace branch)

- [ ] **Step 1: Update imports**

Remove `exportArtifact` and `Artifact` from the `@/lib/api` import **only if unused after this task** — `Artifact` is still used by the `artifacts` state type, so keep it; remove `exportArtifact` (it moved into ArtifactCard). The import block becomes:

```tsx
import {
  AgentEvent,
  Artifact,
  Capability,
  Note,
  Opportunity,
  SettingsView,
  fetchArtifacts,
  fetchCapabilities,
  fetchNotes,
  fetchOpportunities,
  getSettings,
  invokeCapability,
  streamChat,
  updateSettings,
} from "@/lib/api";
import ProfileTab from "./components/ProfileTab";
import ArtifactCard from "./components/ArtifactCard";
```

- [ ] **Step 2: Delete the `BADGE` const**

Remove these lines near the top of the file (they moved into `ArtifactCard.tsx`):

```tsx
const BADGE: Record<Artifact["review_status"], string> = {
  draft: "bg-slate-200 text-slate-700",
  needs_review: "bg-amber-100 text-amber-800",
  approved: "bg-emerald-100 text-emerald-800",
};
```

- [ ] **Step 3: Delete the `doExport` callback**

Remove this block from `Home` (it moved into `ArtifactCard.tsx`):

```tsx
  const doExport = useCallback(async (artifactId: number, format: "docx" | "pdf") => {
    try {
      const r = await exportArtifact(artifactId, format);
      window.location.assign(r.download_url);
    } catch (err) {
      setItems((prev) => [...prev, { kind: "error", text: String(err) }]);
    }
  }, []);
```

- [ ] **Step 4: Replace the artifact map in the workspace branch**

In the workspace `<div>` (the `canvasTab !== "profile"` branch), replace the entire artifacts `<article>` map:

```tsx
              {artifacts.map((a) => (
                <article key={`a-${a.id}`} className="rounded border bg-slate-50 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-semibold">{a.title}</h3>
                    <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                      {a.kind} v{a.version}
                    </span>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${BADGE[a.review_status]}`}
                    >
                      {a.review_status.replace("_", " ")}
                    </span>
                    {(["docx", "pdf"] as const).map((fmt) => (
                      <button
                        key={fmt}
                        className="rounded border px-1.5 py-0.5 text-[10px] font-medium text-slate-600 hover:bg-slate-200"
                        onClick={() => doExport(a.id, fmt)}
                      >
                        {fmt}
                      </button>
                    ))}
                  </div>
                  {a.provenance && (
                    <p className="mt-0.5 text-[11px] text-slate-400">{a.provenance}</p>
                  )}
                  <p className="mt-1 max-h-40 overflow-hidden whitespace-pre-wrap text-sm text-slate-700">
                    {a.body}
                  </p>
                </article>
              ))}
```

with:

```tsx
              {artifacts.map((a) => (
                <ArtifactCard key={`a-${a.id}`} artifact={a} onChanged={refreshCanvas} />
              ))}
```

Leave the notes `<article>` map and the empty-state paragraph exactly as they are.

- [ ] **Step 5: Verify the build**

Run: `NODE_ENV=production npm --prefix frontend run build`
Expected: exit 0, no "unused variable" or "cannot find name BADGE / doExport / exportArtifact" errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(frontend): render ArtifactCard in workspace; export/approve from card"
```

---

### Task 4: Verification (kinds match, backend green, live seam)

**Files:** none (verification only)

- [ ] **Step 1: Frontend GENERATIVE_KINDS matches backend**

Run:
```bash
grep -n 'GENERATIVE_KINDS' /home/drobertson123/src/job-hunt/app/grounding_service.py
grep -n 'GENERATIVE_KINDS' /home/drobertson123/src/job-hunt/frontend/app/components/ArtifactCard.tsx
```
Expected: backend tuple is `("cv", "cover_letter", "pitch", "outreach")` and the frontend const lists the same four strings in the same order. If they differ, fix the frontend const and rebuild.

- [ ] **Step 2: Backend suite still green, no backend diff**

Run: `uv run --extra dev pytest -q`
Expected: `148 passed, 4 skipped` (or current baseline), 0 failures.

Run: `git diff main --stat -- app/ tests/`
Expected: empty output (frontend-only change).

- [ ] **Step 3: Production build**

Run: `NODE_ENV=production npm --prefix frontend run build`
Expected: exit 0.

- [ ] **Step 4: Live seam (server running + corpus + OH_OPENAI_API_KEY)**

With the server up on :8000:

```bash
# Create a generative (cv) artifact tied to an existing opportunity.
OPP=$(curl -s http://localhost:8000/api/opportunities | python3 -c "import json,sys; o=json.load(sys.stdin); print(o[0]['id'] if o else '')")
curl -s -X POST http://localhost:8000/api/artifacts -H 'Content-Type: application/json' \
  -d "{\"kind\":\"cv\",\"title\":\"seam CV\",\"body\":\"# CV\\nLed IIoT platform delivering \$360M value.\\nFluent in Klingon.\",\"opportunity_id\":\"$OPP\"}" | python3 -m json.tool
```

Then in the browser (Workspace tab): expand the new CV card → **Check grounding** (a report appears; the Klingon line should surface as unsupported with a `[MISSING: …]` marker; status badge → "needs review") → **Approve** (badge → "approved"; docx/pdf enable) → click **docx** (a file downloads). Confirm a draft/needs-review CV shows docx/pdf disabled with the "Approve this artifact to export" tooltip, and the existing `fit_analysis` card still exports from draft and shows no Approve UI.

UI-level confirmations are reported to the user, not asserted by a test.

- [ ] **Step 5: Hand off for merge**

Implementation complete → use superpowers:finishing-a-development-branch.
