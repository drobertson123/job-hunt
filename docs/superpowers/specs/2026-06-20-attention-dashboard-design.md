# Design: Attention Tab (read-only)

**Date:** 2026-06-20
**Status:** Approved design — ready for implementation plan

## 1. Purpose

Surface the app's "don't miss opportunities" signal — overdue actions, stale
in-flight opportunities, and untriaged ones — in a read-only Attention tab.
`GET /api/attention` already computes this (`orchestration.needs_attention`);
nothing in the UI shows it today. Continues the opportunity-centric UI build
(after Detail and Board).

## 2. Scope

Frontend-only, additive, read-only: a new "Attention" canvas tab with a counts
summary, grouped items, and click-through to an opportunity's Detail tab. No
backend/schema change.

**Out of scope:** complete/snooze actions from the tab (chosen read-only); a
count badge on the tab label (would need a page-level fetch); routing. Follows
the existing component + `api.ts` patterns (Detail/Board tabs).

## 3. `frontend/lib/api.ts`

```typescript
export type AttentionItem = {
  kind: string;            // "overdue_action" | "stale_opportunity" | "untriaged_opportunity"
  severity: string;        // "high" | "medium" | ...
  opportunity_id: string | null;
  title: string;
  reason: string;
  action_id?: number;      // overdue_action
  due_at?: string | null;  // overdue_action
  stage?: string;          // stale/untriaged
  last_activity_at?: string;  // stale
};

export type Attention = {
  items: AttentionItem[];
  counts: {
    overdue_actions: number;
    stale_opportunities: number;
    untriaged_opportunities: number;
    total: number;
  };
};

export async function fetchAttention(): Promise<Attention> {
  const res = await fetch("/api/attention");
  if (!res.ok) throw new Error(`attention failed: ${res.status}`);
  return res.json();
}
```

(`AttentionItem` is intentionally a loose superset — the backend item dicts vary
by `kind`; optional fields cover the kind-specific keys.)

## 4. `frontend/app/components/AttentionTab.tsx`

Props: `{ onOpen: (oppId: string) => void }`. Fetches attention on mount.

- **Counts summary:** a row of small labelled badges — Overdue
  (`counts.overdue_actions`), Stale (`counts.stale_opportunities`), Untriaged
  (`counts.untriaged_opportunities`), Total (`counts.total`).
- **Empty state:** when `counts.total === 0`, render "Nothing needs attention 🎉".
- **Items:** group `items` by `kind` in a fixed order (overdue_action →
  stale_opportunity → untriaged_opportunity), each group with a small heading.
  Each item row shows: a severity dot (high = red, medium = amber, else slate),
  the `title`, the `reason`, and the kind-specific detail when present —
  `due_at` (formatted) for overdue actions, `stage` + `last_activity_at` for
  stale, `stage` for untriaged.
- **Click:** a row with a non-null `opportunity_id` is clickable → `onOpen(opportunity_id)`.
  Rows without one (an unlinked overdue action) render non-clickable.
- Keys: use `action_id` for overdue actions and `opportunity_id` for opp items;
  fall back to the array index when neither is present.

## 5. `frontend/app/page.tsx`

- Import `AttentionTab`.
- Widen the `canvasTab` union with `"attention"`.
- Add an "Attention" tab button styled exactly like the existing tab buttons.
- Render `<AttentionTab onOpen={(id) => { setSelectedOpp(id); setCanvasTab("detail"); }} />`
  in the ternary chain (before the workspace fallback).
- Self-contained component; no attention state in `page.tsx`; other tabs and the
  workspace block unchanged.

## 6. Testing

Frontend-only; no frontend test harness and none added. Verification is
`npm --prefix frontend run build` ("Compiled successfully", no type errors).
Backend pytest suite untouched (no backend change); the plan's final step runs
`scripts/ci/gate.sh` to confirm no regression.

## 7. Notes

- Zero backend changes; `/api/attention` returns `{items, counts}` already.
- Read-only by design (per the scope decision) keeps the slice small and avoids a
  write path.
- `total === 0` is the current real state (29 opps all `new`, under the untriaged
  threshold, no due-dated actions), so the empty state is what renders until data
  ages or actions get due dates.
