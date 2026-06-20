# Pipeline Board Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A drag-and-drop "Board" canvas tab: opportunities in columns by stage, drag to change stage (logs a Decision), track filter, click-through to Detail.

**Architecture:** Frontend-only. `api.ts` gains `PipelineBoard` + `fetchPipeline`/`updateStage`; a `BoardTab` component renders `@dnd-kit/core` droppable stage columns of draggable cards and PATCHes stage on drop; `page.tsx` adds a tab wired to select + jump to Detail. Reuses the existing `GET /api/pipeline` and `PATCH /api/opportunities/{id}/stage` endpoints — no backend change.

**Tech Stack:** Next.js (App Router, static export), React 18, TypeScript, Tailwind, `@dnd-kit/core`.

## Global Constraints

- Frontend-only, additive. No backend/schema changes (`/api/pipeline`, `/api/opportunities/{id}/stage` already exist).
- New dependency: `@dnd-kit/core` ONLY (no `@dnd-kit/sortable`, no `@dnd-kit/utilities` — compute the drag transform inline). Install with `npm --prefix frontend install @dnd-kit/core`.
- No frontend test harness; per-task verification is `npm --prefix frontend run build` ("Compiled successfully", no type errors), run from the worktree root.
- Reuse `OpportunityFull` (already in `api.ts` from the detail slice). Stage values come from `board.columns` (server-authoritative), never hardcoded.
- Drag-vs-click: a `PointerSensor` with `activationConstraint: { distance: 5 }` so a plain click is not a drag.
- Drag to a different column → `updateStage(id, newStage, "moved via board")`; same column/no target → no-op; on error, refetch to revert.
- Tab button styling copies the existing tab buttons verbatim (`` className={`border-b-2 py-2 ${canvasTab === "X" ? "border-slate-900 text-slate-900" : "border-transparent text-slate-400 hover:text-slate-600"}`} ``).

---

### Task 1: api.ts — board types + fetchers

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Consumes: existing `OpportunityFull`.
- Produces: `PipelineBoard` type; `fetchPipeline(type?: "job" | "business"): Promise<PipelineBoard>`; `updateStage(oppId: string, stage: string, rationale: string): Promise<OpportunityFull>`.

- [ ] **Step 1: Add the types + fetchers**

Append to `frontend/lib/api.ts`:

```typescript
export type PipelineBoard = {
  columns: string[];
  by_stage: Record<string, OpportunityFull[]>;
};

export async function fetchPipeline(type?: "job" | "business"): Promise<PipelineBoard> {
  const qs = type ? `?type=${type}` : "";
  const res = await fetch(`/api/pipeline${qs}`);
  if (!res.ok) throw new Error(`pipeline failed: ${res.status}`);
  return res.json();
}

export async function updateStage(
  oppId: string,
  stage: string,
  rationale: string,
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

- [ ] **Step 2: Verify it builds**

Run: `npm --prefix frontend run build`
Expected: "Compiled successfully", no type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(ui): pipeline board types + fetchPipeline/updateStage"
```

---

### Task 2: @dnd-kit/core dependency + BoardTab component

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json` (via npm install)
- Create: `frontend/app/components/BoardTab.tsx`

**Interfaces:**
- Consumes: `PipelineBoard`, `OpportunityFull`, `fetchPipeline`, `updateStage` (Task 1).
- Produces: `<BoardTab onOpen={(oppId: string) => void} />`.

- [ ] **Step 1: Install the dependency**

Run: `npm --prefix frontend install @dnd-kit/core`
Expected: adds `@dnd-kit/core` to `frontend/package.json` dependencies and updates `package-lock.json`; exits 0.

- [ ] **Step 2: Create `frontend/app/components/BoardTab.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  DndContext,
  DragEndEvent,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { OpportunityFull, PipelineBoard, fetchPipeline, updateStage } from "@/lib/api";

type Filter = "all" | "job" | "business";

function Card({ opp, onOpen }: { opp: OpportunityFull; onOpen: (id: string) => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: opp.id,
  });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined;
  return (
    <div
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      onClick={() => onOpen(opp.id)}
      className={`cursor-grab rounded border border-slate-200 bg-white p-2 text-sm shadow-sm ${
        isDragging ? "opacity-50" : ""
      }`}
    >
      <div className="font-medium">{opp.title}</div>
      <div className="flex items-center gap-2 text-xs text-slate-500">
        {opp.organization}
        {opp.fit_score != null && (
          <span className="rounded bg-slate-100 px-1.5 py-0.5">Fit {opp.fit_score}</span>
        )}
      </div>
    </div>
  );
}

function Column({
  stage,
  opps,
  onOpen,
}: {
  stage: string;
  opps: OpportunityFull[];
  onOpen: (id: string) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: stage });
  return (
    <div
      ref={setNodeRef}
      className={`flex w-56 shrink-0 flex-col gap-2 rounded p-2 ${
        isOver ? "bg-slate-100" : "bg-slate-50"
      }`}
    >
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {stage} ({opps.length})
      </h3>
      {opps.map((o) => (
        <Card key={o.id} opp={o} onOpen={onOpen} />
      ))}
    </div>
  );
}

export default function BoardTab({ onOpen }: { onOpen: (oppId: string) => void }) {
  const [board, setBoard] = useState<PipelineBoard | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  const load = useCallback(() => {
    fetchPipeline(filter === "all" ? undefined : filter)
      .then(setBoard)
      .catch(() => setBoard(null));
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || !board) return;
    const oppId = String(active.id);
    const newStage = String(over.id);
    // find the card + its current stage
    let from: string | null = null;
    let card: OpportunityFull | undefined;
    for (const [stage, opps] of Object.entries(board.by_stage)) {
      const found = opps.find((o) => o.id === oppId);
      if (found) {
        from = stage;
        card = found;
        break;
      }
    }
    if (!card || from === null || from === newStage) return;
    // optimistic move
    const next: PipelineBoard = {
      columns: board.columns,
      by_stage: Object.fromEntries(
        board.columns.map((s) => [s, [...(board.by_stage[s] ?? [])]]),
      ),
    };
    next.by_stage[from] = next.by_stage[from].filter((o) => o.id !== oppId);
    next.by_stage[newStage] = [...(next.by_stage[newStage] ?? []), { ...card, stage: newStage }];
    setBoard(next);
    updateStage(oppId, newStage, "moved via board").catch(() => load());
  };

  if (!board) {
    return <p className="p-4 text-sm text-slate-400">Loading…</p>;
  }

  const total = board.columns.reduce((n, s) => n + (board.by_stage[s]?.length ?? 0), 0);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex gap-1 p-2">
        {(["all", "job", "business"] as Filter[]).map((f) => (
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
      {total === 0 ? (
        <p className="p-4 text-sm text-slate-400">No opportunities in this view.</p>
      ) : (
        <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
          <div className="flex min-h-0 flex-1 gap-2 overflow-x-auto p-2">
            {board.columns.map((stage) => (
              <Column key={stage} stage={stage} opps={board.by_stage[stage] ?? []} onOpen={onOpen} />
            ))}
          </div>
        </DndContext>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify it builds**

Run: `npm --prefix frontend run build`
Expected: "Compiled successfully", no type errors (confirms `@dnd-kit/core` resolves and the component typechecks).

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/app/components/BoardTab.tsx
git commit -m "feat(ui): drag-and-drop BoardTab with @dnd-kit/core"
```

---

### Task 3: page.tsx wiring

**Files:**
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `<BoardTab onOpen=... />` (Task 2); existing `selectedOpp`/`setSelectedOpp`/`setCanvasTab`.

- [ ] **Step 1: Wire the Board tab**

Read `frontend/app/page.tsx` first. Then:

1. Add the import beside the other component imports:
```tsx
import BoardTab from "./components/BoardTab";
```
2. Widen the `canvasTab` union (the existing `useState<...>` line) to add `"board"`:
```tsx
  const [canvasTab, setCanvasTab] = useState<
    "workspace" | "profile" | "applications" | "briefing" | "detail" | "board"
  >("workspace");
```
3. Add a "Board" tab button AFTER the Detail button (verbatim style — copy the exact className expression from an existing button, substituting `"board"`):
```tsx
            <button
              className={`border-b-2 py-2 ${
                canvasTab === "board"
                  ? "border-slate-900 text-slate-900"
                  : "border-transparent text-slate-400 hover:text-slate-600"
              }`}
              onClick={() => setCanvasTab("board")}
            >
              Board
            </button>
```
4. Add a render branch in the ternary chain, before the final workspace `) : (`:
```tsx
          ) : canvasTab === "board" ? (
            <BoardTab
              onOpen={(id) => {
                setSelectedOpp(id);
                setCanvasTab("detail");
              }}
            />
```

Do NOT add board state to `page.tsx`; leave the workspace block and other tabs unchanged.

- [ ] **Step 2: Verify it builds**

Run: `npm --prefix frontend run build`
Expected: "Compiled successfully", no type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(ui): wire Board tab (click-through to Detail)"
```

---

## Final verification

- [ ] `npm --prefix frontend run build` → Compiled successfully.
- [ ] `scripts/ci/gate.sh` → GATE PASSED (backend suite unaffected; confirms no regression).
- [ ] `git log --oneline` shows 3 focused commits on `feature/pipeline-board`.

## Self-Review (completed by plan author)

- **Spec coverage:** `@dnd-kit/core` only, inline transform (T2, spec §3 + global constraint); board types + fetchers (T1, §4); BoardTab with droppable stage columns, draggable cards, PointerSensor distance-5, drag→updateStage + optimistic move + revert-on-error, track filter, click→onOpen (T2, §5); page wiring with `setSelectedOpp`+`setCanvasTab("detail")`, no board state in page.tsx (T3, §6); build-only verification (all tasks, §7); stages from `board.columns` not hardcoded (T2).
- **Placeholder scan:** none — full component code; page.tsx edits give verbatim button/branch code.
- **Type consistency:** `fetchPipeline(type?)`/`updateStage(oppId, stage, rationale)` signatures identical across T1 def and T2 usage. `PipelineBoard.by_stage` is `Record<string, OpportunityFull[]>`; the component reads `opp.id/title/organization/fit_score/stage` — all on `OpportunityFull`. `DragEndEvent`/`useDraggable`/`useDroppable`/`PointerSensor`/`useSensor`/`useSensors`/`DndContext` are all `@dnd-kit/core` exports. `onOpen` signature matches between T2 prop and T3 caller.
