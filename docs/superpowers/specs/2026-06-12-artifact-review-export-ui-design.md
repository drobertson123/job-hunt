# Artifact Review & Export UI — unblock generative-artifact export

**Date:** 2026-06-12
**Status:** Approved design, not yet implemented
**Decided with user:** inline-expand review UI on each artifact card (over modal
/ drawer); the review view also shows the full readable body (fixing the
truncated, unreadable card); review/approve flow applies only to generative
kinds, non-generative cards just gain a read-the-full-body expand.

## Goal

Today a tailored CV or cover letter cannot leave the app through the UI. Export
is gated — generative artifact kinds (`cv`, `cover_letter`, `pitch`,
`outreach`) must be `approved` (`export_service.py:119`). After any skill run,
auto-grounding moves those artifacts to `needs_review`
(`grounding_service.py:218`), and the only way forward is the approve endpoint
(`needs_review → approved`). The UI has **no approve action and no grounding
view**, and it shows the docx/pdf buttons on every artifact regardless — so
exporting a generative artifact just 409s. This builds the missing review flow
so generative artifacts can be checked, approved, and exported from the UI.

## Scope

- **In:** per-artifact inline-expand "Review" UI (grounding report + full body +
  Check/Re-check + Approve for generative kinds; full-body read for all kinds);
  export-button gating so export is only offered when it will succeed; API
  client functions for the grounding/approve endpoints; extraction of artifact
  rendering from `page.tsx` into a focused `ArtifactCard` component.
- **Out:** backend changes of any kind; opportunity detail / pipeline board /
  attention dashboard / actions UI (the larger interface redesign — separate
  spec); editing artifact bodies in-canvas; manual artifact creation UI;
  grounding/approve UI for non-generative kinds (they don't need it).

## Backend contract (already implemented — read-only reference)

- `POST /api/artifacts/{id}/grounding` → `GroundingOut`; runs the
  embedding-similarity check, **sets `review_status = needs_review`**, returns
  the report. 400 on missing OpenAI key / empty corpus, 404 on missing artifact.
- `GET /api/artifacts/{id}/grounding` → `GroundingOut`; **404 with detail "no
  grounding report — run a check first"** when none exists.
- `POST /api/artifacts/{id}/approve` → `Artifact`; `needs_review → approved`.
  **409** (`InvalidStatusTransition`) from any other status, 404 if missing.
- `GroundingOut` fields: `artifact_id, threshold, embedding_model,
  checked_count, unsupported_count, findings: list[dict], annotated_body: str,
  stale: bool, created_at`. `annotated_body` already contains literal
  `[MISSING: …]` markers at unsupported spans; when `stale` is true the server
  returns the **unannotated** body (stale offsets are not applied).
- A `finding` dict: `{text, start, end, score, chunk_id, document_title,
  supported}`.
- Export gate: `artifact.kind in GENERATIVE_KINDS and review_status !=
  approved` → 409; all other cases export from any status.
- `GENERATIVE_KINDS = ("cv", "cover_letter", "pitch", "outreach")`
  (`grounding_service.py:254`).

## 1. Component structure

```
frontend/app/components/ArtifactCard.tsx   # new — one artifact, owns review state
frontend/lib/api.ts                        # extended — grounding/approve types + fns
frontend/app/page.tsx                      # modified — render <ArtifactCard/>, drop inline markup
```

`ArtifactCard` is self-contained: props `{ artifact: Artifact; onChanged: () =>
void }`. It owns `expanded`, `report: GroundingReport | null`, `busy`
(check/approve in flight), and `error: string | null`. After a successful
check or approve it calls `onChanged()` so `page.tsx`'s `refreshCanvas()`
re-pulls the artifact list (refreshing the status badge and export gating).

`page.tsx` keeps the workspace branch but replaces the inline `<article>` map
with `{artifacts.map((a) => <ArtifactCard key={a.id} artifact={a}
onChanged={refreshCanvas} />)}`. Note rendering stays inline (trivial). The
`BADGE` map and `doExport` move into `ArtifactCard` (export is now a
card-local concern); `exportArtifact` stays in `api.ts`.

## 2. API client additions (`frontend/lib/api.ts`)

Follow the existing `throwDetail` convention.

```ts
export type GroundingFinding = {
  text: string; start: number; end: number; score: number;
  chunk_id: number | null; document_title: string | null; supported: boolean;
};
export type GroundingReport = {
  artifact_id: number; threshold: number; embedding_model: string;
  checked_count: number; unsupported_count: number;
  findings: GroundingFinding[]; annotated_body: string;
  stale: boolean; created_at: string;
};

runGrounding(id: number): Promise<GroundingReport>     // POST /grounding (throwDetail)
getGrounding(id: number): Promise<GroundingReport | null>  // GET /grounding; 404 → null
approveArtifact(id: number): Promise<Artifact>         // POST /approve (throwDetail)
```

`getGrounding` is the one special case: a 404 means "no report yet" (a normal
state, not an error), so it returns `null`; any other non-OK status throws via
`throwDetail`.

## 3. ArtifactCard behavior

**Generative-kinds source of truth.** A module const
`GENERATIVE_KINDS = ["cv", "cover_letter", "pitch", "outreach"] as const` with
a comment: `// mirror of grounding_service.py GENERATIVE_KINDS`. Helper
`isGenerative(kind)` and `canExport(artifact) = !isGenerative(artifact.kind) ||
artifact.review_status === "approved"`.

**Collapsed card** (unchanged from today plus a toggle): title, `{kind}
v{version}` chip, status badge, a short truncated body preview
(`max-h-40 overflow-hidden`), provenance line, a **Review** toggle button, and
the docx/pdf controls.

**Export controls:** if `canExport(artifact)`, render docx/pdf as today
(clickable, calls `doExport`). Otherwise render them **disabled** with
`title="Approve this artifact to export"`.

**Expanded view** (`expanded === true`): on first expand, call
`getGrounding(id)` and store the result (null is fine). Then:
- **Full body**, scrollable (own block, `max-h-96 overflow-y-auto`,
  `whitespace-pre-wrap`): show `report.annotated_body` when a report exists and
  `!report.stale`, otherwise `artifact.body`. The `[MISSING: …]` markers render
  as plain inline text (already in the annotated body).
- **Generative kinds only**, a review section:
  - Summary line when a report exists: `{unsupported_count} of {checked_count}
    claims unsupported · threshold {threshold}`. If `report.stale`, an amber
    note: "Document changed since the last check — re-check before approving."
    If no report yet: "No grounding check yet."
  - **Check grounding** / **Re-check** button (label depends on whether a
    report exists) → `runGrounding(id)`, sets `busy`, label "Checking…" while
    running; on success store the new report, clear error, call `onChanged()`.
  - **Approve** button, enabled only when `artifact.review_status ===
    "needs_review"`; on success clear error and call `onChanged()`. When the
    status is `draft`, show it disabled with `title="Run a grounding check
    first"`; when already `approved`, omit the button.
- **Error strip** inside the expanded area showing the server `detail` verbatim
  (missing OpenAI key, empty corpus, 409). New errors replace; success clears.

Non-generative kinds show only the full-body block on expand — no summary,
check, or approve.

## 4. Error handling

| Failure | Surfaced as |
|---|---|
| 400 missing OpenAI key (grounding) | error strip, server detail |
| 400 empty corpus (grounding) | error strip |
| 409 invalid transition (approve) | error strip |
| 409 export not allowed | cannot occur — export disabled until approved |
| network/5xx | error strip with status fallback |

## 5. Testing & verification

No backend changes — `uv run --extra dev pytest -q` stays green (148 passed /
4 skipped) and `git diff main --stat -- app/ tests/` is empty.

Frontend (repo convention: no unit-test infra, the build is the gate):
1. `NODE_ENV=production npm --prefix frontend run build` exits 0.
2. A plan task asserts the frontend `GENERATIVE_KINDS` const equals the backend
   tuple (grep both; they must match exactly).
3. Live seam (server running, corpus + `OH_OPENAI_API_KEY` live): create a `cv`
   artifact (`POST /api/artifacts` with `kind=cv`, a body, an `opportunity_id`)
   → in the UI, expand it → **Check grounding** (report appears, status →
   needs review, body shows `[MISSING: …]` where unsupported) → **Approve**
   (badge → approved, export buttons enable) → **export docx** downloads. Also
   confirm a generative artifact in draft/needs_review shows export disabled
   with the tooltip, and a non-generative artifact (the existing fit_analysis)
   still exports from draft and shows no approve UI.
