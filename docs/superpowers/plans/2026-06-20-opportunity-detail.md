# Opportunity Detail Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only "Detail" canvas tab that renders the full `GET /api/opportunities/{id}` aggregate for the selected opportunity.

**Architecture:** Frontend-only. `frontend/lib/api.ts` gains the aggregate types + a fetcher; a self-contained `OpportunityDetailTab` component renders header + briefing/applications/actions/artifacts/decisions sections; `page.tsx` adds a tab keyed to the existing `selectedOpp`. Zero backend changes (the endpoint and all six includes already exist).

**Tech Stack:** Next.js (App Router), React, TypeScript, Tailwind.

## Global Constraints

- Frontend-only, additive, READ-ONLY: no editing/stage-change/archive; no duplicating ArtifactCard's review/export; no routing; no backend/schema changes.
- No frontend test harness exists; verification per task is `npm --prefix frontend run build` ("Compiled successfully", no type errors). Run from the worktree root.
- Reuse existing types (`Application`, `Briefing`, `Artifact`) and the exact `fetch` idiom already in `frontend/lib/api.ts`. The minimal `Opportunity` type (dropdown) stays unchanged; `OpportunityFull` is the detail shape.
- Tab button styling must copy the existing Profile/Applications/Briefing button markup verbatim (`` className={`border-b-2 py-2 ${canvasTab === "X" ? "border-slate-900 text-slate-900" : "border-transparent text-slate-400 hover:text-slate-600"}`} ``).
- `key`: use stable ids (`a.id`) where available; array index only for briefing facts (`BriefingFactKey` can repeat).

---

### Task 1: api.ts — aggregate types + fetcher

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Consumes: existing `Application`, `Briefing`, `Artifact` types.
- Produces: `OpportunityFull`, `Action`, `Decision`, `OpportunityDetail` types; `fetchOpportunityDetail(oppId: string): Promise<OpportunityDetail>`.

- [ ] **Step 1: Add the types + fetcher**

Append to `frontend/lib/api.ts` (after the existing `Briefing`/`Application` types and fetchers):

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

- [ ] **Step 2: Verify it builds**

Run: `npm --prefix frontend run build`
Expected: "Compiled successfully", no type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(ui): OpportunityDetail aggregate types + fetcher"
```

---

### Task 2: OpportunityDetailTab component + page wiring

**Files:**
- Create: `frontend/app/components/OpportunityDetailTab.tsx`
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `OpportunityDetail`, `fetchOpportunityDetail` (Task 1); existing `selectedOpp` state in `page.tsx`.
- Produces: `<OpportunityDetailTab opportunityId={...} />`.

- [ ] **Step 1: Create `frontend/app/components/OpportunityDetailTab.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { OpportunityDetail, fetchOpportunityDetail } from "@/lib/api";

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs uppercase text-slate-600">
      {children}
    </span>
  );
}

function Section({ title, count, children }: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {title} ({count})
      </h3>
      {count === 0 ? (
        <p className="text-sm text-slate-400">None.</p>
      ) : (
        <div className="flex flex-col gap-1">{children}</div>
      )}
    </div>
  );
}

export default function OpportunityDetailTab({ opportunityId }: { opportunityId: string }) {
  const [detail, setDetail] = useState<OpportunityDetail | null>(null);

  const load = useCallback(() => {
    if (!opportunityId) {
      setDetail(null);
      return;
    }
    fetchOpportunityDetail(opportunityId).then(setDetail).catch(() => setDetail(null));
  }, [opportunityId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!opportunityId) {
    return (
      <p className="p-4 text-sm text-slate-400">
        Select an opportunity above to see its detail.
      </p>
    );
  }
  if (!detail) {
    return <p className="p-4 text-sm text-slate-400">Loading…</p>;
  }

  const o = detail.opportunity;
  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 text-sm">
      {/* Header */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold">{o.title}</h2>
          <Badge>{o.stage}</Badge>
          {o.fit_score != null && <Badge>Fit {o.fit_score}</Badge>}
        </div>
        <div className="text-xs text-slate-500">
          {o.organization}
          {o.location && ` · ${o.location}`}
          {o.url && (
            <>
              {" · "}
              <a href={o.url} target="_blank" rel="noreferrer" className="text-blue-600 underline">
                link
              </a>
            </>
          )}
        </div>
        {o.summary && <p className="text-slate-700">{o.summary}</p>}
      </div>

      <Section title="Briefing" count={detail.briefing ? 1 : 0}>
        {detail.briefing && (
          <div className="flex flex-col gap-1">
            {detail.briefing.summary && (
              <p className="text-slate-700">{detail.briefing.summary}</p>
            )}
            {detail.briefing.facts.map((f, i) => (
              <div key={i} className="rounded border border-slate-200 p-2">
                <div className="font-medium">{f.question}</div>
                <div>{f.answer}</div>
                <div className="text-xs text-slate-500">
                  {f.confidence != null && `confidence ${f.confidence.toFixed(2)}`}
                  {f.source && ` · source: ${f.source}`}
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title="Applications" count={detail.applications.length}>
        {detail.applications.map((a) => (
          <div key={a.id} className="flex items-center gap-2 rounded border border-slate-200 p-2">
            <Badge>{a.status}</Badge>
            {a.portal_url && (
              <a href={a.portal_url} target="_blank" rel="noreferrer" className="text-xs text-blue-600 underline">
                portal
              </a>
            )}
            {a.submitted_at && (
              <span className="text-xs text-slate-500">
                {new Date(a.submitted_at).toLocaleDateString()}
              </span>
            )}
          </div>
        ))}
      </Section>

      <Section title="Actions" count={detail.actions.length}>
        {detail.actions.map((a) => (
          <div key={a.id} className="flex items-center gap-2 rounded border border-slate-200 p-2">
            <Badge>{a.status}</Badge>
            <span>{a.title}</span>
            <span className="text-xs text-slate-400">{a.kind}</span>
            {a.due_at && (
              <span className="text-xs text-slate-500">
                due {new Date(a.due_at).toLocaleDateString()}
              </span>
            )}
          </div>
        ))}
      </Section>

      <Section title="Artifacts" count={detail.artifacts.length}>
        {detail.artifacts.map((a) => (
          <div key={a.id} className="flex items-center gap-2 rounded border border-slate-200 p-2">
            <Badge>{a.review_status}</Badge>
            <span>{a.title}</span>
            <span className="text-xs text-slate-400">{a.kind} v{a.version}</span>
          </div>
        ))}
      </Section>

      <Section title="Decisions" count={detail.decisions.length}>
        {detail.decisions.map((d) => (
          <div key={d.id} className="rounded border border-slate-200 p-2">
            <Badge>{d.kind}</Badge> <span>{d.summary}</span>
          </div>
        ))}
      </Section>
    </div>
  );
}
```

- [ ] **Step 2: Wire into `frontend/app/page.tsx`**

1. Add the import beside the other component imports:
```tsx
import OpportunityDetailTab from "./components/OpportunityDetailTab";
```
2. Widen the `canvasTab` union (the existing line):
```tsx
  const [canvasTab, setCanvasTab] = useState<
    "workspace" | "profile" | "applications" | "briefing" | "detail"
  >("workspace");
```
3. Add a "Detail" tab button AFTER the Briefing button (verbatim style):
```tsx
            <button
              className={`border-b-2 py-2 ${
                canvasTab === "detail"
                  ? "border-slate-900 text-slate-900"
                  : "border-transparent text-slate-400 hover:text-slate-600"
              }`}
              onClick={() => setCanvasTab("detail")}
            >
              Detail
            </button>
```
4. Add a render branch in the ternary, before the final `) : (` workspace fallback:
```tsx
          ) : canvasTab === "detail" ? (
            <OpportunityDetailTab opportunityId={selectedOpp} />
```
(So the chain reads `profile ? … : applications ? … : briefing ? … : detail ? <OpportunityDetailTab …/> : (workspace)`.)

Do NOT add detail state to `page.tsx`; leave the workspace block and other tabs unchanged.

- [ ] **Step 3: Verify it builds**

Run: `npm --prefix frontend run build`
Expected: "Compiled successfully", no type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/OpportunityDetailTab.tsx frontend/app/page.tsx
git commit -m "feat(ui): read-only Opportunity Detail canvas tab"
```

---

## Final verification

- [ ] `npm --prefix frontend run build` → Compiled successfully.
- [ ] `scripts/ci/gate.sh` → GATE PASSED (backend suite unaffected; confirms no regression).
- [ ] `git log --oneline` shows 2 focused commits on `feature/opportunity-detail`.

## Self-Review (completed by plan author)

- **Spec coverage:** aggregate types + fetcher (T1, spec §3); component header w/ fit_score + all five sections, read-only, empty states (T2, §4); page wiring with `selectedOpp`, no detail state in page.tsx (T2, §5); build-only verification (both tasks, §6).
- **Placeholder scan:** none — full component code provided; page.tsx edits reference the verbatim existing button style (the same approach prior tab tasks used successfully).
- **Type consistency:** `OpportunityDetail` field names match the backend `get_opportunity` dict keys (`opportunity`, `actions`, `artifacts`, `decisions`, `applications`, `briefing`); `Action`/`Decision`/`OpportunityFull` fields match the SQLModel columns; `Artifact`/`Application`/`Briefing` reuse existing types whose fields the component reads (`review_status`, `version`, `kind`, `status`, `portal_url`, `submitted_at`, `facts`, `confidence`, `source`). `fetchOpportunityDetail` mirrors the existing `fetch` idiom.
