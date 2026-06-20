# Design: Opportunity Detail Tab (frontend-only)

**Date:** 2026-06-20
**Status:** Approved design — ready for implementation plan

## 1. Purpose

Give each opportunity a single read-only view that aggregates everything the
backend already knows about it — header (incl. `fit_score`, shown nowhere
today), briefing, applications, actions, artifacts, decisions. Closes the
biggest UI gap (~30% of the backend exposed) without a backend change: the
`GET /api/opportunities/{id}` endpoint already returns the full aggregate
(`opportunity`, `actions`, `artifacts`, `decisions`, `applications`, `briefing`).

## 2. Scope

Frontend-only, additive: a new "Detail" canvas tab keyed to the existing
`selectedOpp` dropdown. Read-only. No routing; no backend/schema changes; the
standalone Applications/Briefing tabs stay.

**Out of scope:** editing / stage changes / archive from the detail view;
duplicating `ArtifactCard`'s grounding/approve/export (that stays in Workspace);
routed pages. Follows existing component + `api.ts` patterns
(`ApplicationsTab`/`BriefingTab`, `fetchArtifacts`).

## 3. `frontend/lib/api.ts`

Add types for the aggregate (reusing existing `Application`, `Briefing`,
`Artifact`):

```typescript
export type OpportunityFull = {
  id: string;
  type: string;
  title: string;
  organization: string | null;
  source: string | null;
  url: string | null;
  location: string | null;
  stage: string;
  fit_score: number | null;
  summary: string | null;
  details: Record<string, unknown>;
  archived: boolean;
  created_at: string;
  updated_at: string;
  last_activity_at: string;
};

export type Action = {
  id: number;
  title: string;
  detail: string;
  kind: string;
  status: string;
  due_at: string | null;
  opportunity_id: string | null;
};

export type Decision = {
  id: number;
  kind: string;
  summary: string;
  rationale: string;
  created_at: string;
};

export type OpportunityDetail = {
  opportunity: OpportunityFull;
  actions: Action[];
  artifacts: Artifact[];
  decisions: Decision[];
  applications: Application[];
  briefing: Briefing | null;
};

export async function fetchOpportunityDetail(oppId: string): Promise<OpportunityDetail> {
  const res = await fetch(`/api/opportunities/${oppId}`);
  if (!res.ok) throw new Error(`opportunity detail failed: ${res.status}`);
  return res.json();
}
```

(Mirror the existing fetch idiom exactly. The minimal `Opportunity` type used by
the dropdown stays as-is; `OpportunityFull` is the detail shape.)

## 4. `frontend/app/components/OpportunityDetailTab.tsx`

Props: `{ opportunityId: string }`. On mount / when `opportunityId` changes,
`fetchOpportunityDetail`. Empty/prompt state when `opportunityId` is falsy or the
fetch fails.

Layout (read-only, stacked sections; each section shows an empty-state line when
its collection is empty):

- **Header:** `title`; `organization`; a stage badge (`stage`); `fit_score`
  rendered when non-null (e.g. "Fit 72"); `location`; external `url` as a link
  when present; `summary`.
- **Briefing:** `briefing.summary` + each fact (question → answer, with
  confidence and source when present). No synthesize button (that lives on the
  Briefing tab). "No briefing yet." when `briefing` is null.
- **Applications:** per row — status badge, portal link (if any), submitted date
  (if any).
- **Actions:** per row — title, kind, status, due date (if any).
- **Artifacts:** per row — title, kind, review-status badge. Read-only list
  (full review/export stays in Workspace). 
- **Decisions:** per row — kind + summary (the activity log).

Use `key` props that are stable where the item has a unique id (`a.id`), and
array index only for the briefing facts (where `BriefingFactKey` can repeat).

## 5. `frontend/app/page.tsx`

- Import `OpportunityDetailTab`.
- Widen the `canvasTab` union with `"detail"`.
- Add a "Detail" tab button styled exactly like the existing Profile/
  Applications/Briefing buttons (copy the real className strings from the file).
- In the render switch, add a branch rendering
  `<OpportunityDetailTab opportunityId={selectedOpp} />`.
- Do NOT add detail state to `page.tsx` (the component is self-contained).
- Leave the workspace block and other tabs unchanged.

## 6. Testing

Frontend-only; no frontend test harness exists and none is added. Verification is
`npm --prefix frontend run build` ("Compiled successfully", no type errors). The
backend pytest suite is untouched (no backend changes), but the plan's final
step still runs `scripts/ci/gate.sh` to confirm nothing regressed.

## 7. Notes

- Zero backend changes: the aggregate endpoint and all six includes already
  exist (applications + briefing were added 2026-06-20).
- Read-only by design keeps the slice small and avoids duplicating the
  Workspace ArtifactCard's review/approve/export affordances.
- `details` is rendered minimally or omitted (a `Record<string, unknown>`); the
  header focuses on the high-signal fields. If shown, render as simple
  key/value text, never as raw JSON dumped at the user.
