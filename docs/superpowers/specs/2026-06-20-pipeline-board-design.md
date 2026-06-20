# Design: Pipeline Board Tab (drag-and-drop)

**Date:** 2026-06-20
**Status:** Approved design — ready for implementation plan

## 1. Purpose

Make the opportunity pipeline visible and manageable: a board with a column per
stage, opportunity cards, drag-to-move (which changes stage and logs a
Decision), a track filter, and click-through to the Detail tab. Today
opportunities are only dropdown entries; this is the next step of the
opportunity-centric UI (after Detail). The `GET /api/pipeline` and
`PATCH /api/opportunities/{id}/stage` endpoints already exist — no backend
change.

## 2. Scope

Frontend-only, additive: a new "Board" canvas tab. Adds one npm dependency
(`@dnd-kit/core`). Drag-to-move is a write path (stage change → Decision).

**Out of scope:** reordering cards within a column (`@dnd-kit/sortable`); won/lost
archive actions from the board; keyboard-DnD refinements; any backend change.
Follows existing component + `api.ts` patterns.

## 3. Dependency

Add `@dnd-kit/core` (only). It provides `DndContext`, `useDraggable`,
`useDroppable`, and `PointerSensor` with an activation distance — enough to move
cards between columns and to cleanly distinguish a click from a drag. No
`@dnd-kit/sortable` (no within-column ordering).

## 4. `frontend/lib/api.ts`

```typescript
export type PipelineBoard = {
  columns: string[];
  by_stage: Record<string, OpportunityFull[]>;  // OpportunityFull from the detail slice
};

export async function fetchPipeline(type?: "job" | "business"): Promise<PipelineBoard> {
  const qs = type ? `?type=${type}` : "";
  const res = await fetch(`/api/pipeline${qs}`);
  if (!res.ok) throw new Error(`pipeline failed: ${res.status}`);
  return res.json();
}

export async function updateStage(
  oppId: string, stage: string, rationale: string
): Promise<OpportunityFull> {
  const res = await fetch(`/api/opportunities/${oppId}/stage`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stage, rationale }),
  });
  if (!res.ok) throw new Error(`update stage failed: ${res.status}`);
  return res.json();
}
```

(`OpportunityFull` already exists in `api.ts` from the opportunity-detail slice.)

## 5. `frontend/app/components/BoardTab.tsx`

Props: `{ onOpen: (oppId: string) => void }`.

State: `board: PipelineBoard | null`, `filter: "all" | "job" | "business"`.

- On mount and on `filter` change, `fetchPipeline(filter === "all" ? undefined : filter)`.
- **Track filter:** a small segmented control (All / Job / Business) that sets
  `filter`.
- **Layout:** a horizontally-scrollable row of columns, one per
  `board.columns` entry (stage value as the header + a count). Each column is a
  `useDroppable` keyed by the stage. Each card is a `useDraggable` keyed by the
  opportunity id, showing title, organization, and a `fit_score` badge when
  non-null.
- **DndContext** wraps the board with a `PointerSensor` configured with an
  activation constraint (`distance: 5`) so a small movement is a drag and a plain
  click is not.
- **On drag end:** if the card was dropped over a column whose stage differs from
  the card's current stage, optimistically move the card in local state, then
  `updateStage(id, newStage, "moved via board")`; on error, refetch to revert.
  If dropped on the same column (or outside), do nothing.
- **On card click (no drag):** `onOpen(id)`.
- Empty state when there are no opportunities; per-column empty space is allowed.

## 6. `frontend/app/page.tsx`

- Import `BoardTab`.
- Widen the `canvasTab` union with `"board"`.
- Add a "Board" tab button styled exactly like the existing tab buttons.
- Render in the ternary:
  `<BoardTab onOpen={(id) => { setSelectedOpp(id); setCanvasTab("detail"); }} />`
  (reuses the existing `setSelectedOpp` setter and the Detail tab).
- Do not add board state to `page.tsx` (the component is self-contained); leave
  other tabs and the workspace block unchanged.

## 7. Testing

Frontend-only; no frontend test harness exists and none is added. Verification is
`npm --prefix frontend run build` ("Compiled successfully", no type errors). The
drag→PATCH path is type-checked by the build and smoke-tested manually when the
app is run. Backend pytest suite is untouched; the plan's final step still runs
`scripts/ci/gate.sh` to confirm no regression.

## 8. Notes / risks

- Adds an npm dependency — `npm --prefix frontend install @dnd-kit/core` needs
  network; it updates `frontend/package.json` + `package-lock.json`.
- Write path: dragging changes stage and logs a Decision (`rationale="moved via
  board"`), unlike the prior read-only tabs. The same endpoint the agent uses
  (`set_stage`) backs it, so behavior is consistent.
- `@dnd-kit/core` is a client-only concern; `BoardTab` is a `"use client"`
  component, fine for the Next.js static export.
- Stage values are taken from `board.columns` (server-authoritative order), not
  hardcoded in the component.
