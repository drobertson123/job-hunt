# Board Insight Rail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add the Job Hunter design's right **insight rail** to the Board — "Needs your decision" (attention), an "Automation activity" feed (recent agent runs), and a dark mini-metrics card — as a **resizable** split next to the kanban.

## Global Constraints
- Wire to REAL data (no fabricated numbers): attention items, recent runs, applications, opportunities.
- pytest: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest …`. Frontend: `npm --prefix frontend install` then build. Verify: `bash scripts/ci/gate.sh` GREEN + frontend build.
- Do NOT invoke any finishing/branch skill — stop after committing and reporting.

---

### Task 1: `GET /api/runs` list endpoint

**Files:** Modify `app/routers/runs.py`; Test `tests/test_runs_list.py`.

- [ ] **Step 1: Failing test**

Create `tests/test_runs_list.py`:
```python
from sqlmodel import Session
from app.db import engine
from app.models import Run, RunStatus


def test_runs_list_returns_recent(client):
    with Session(engine) as s:
        s.add(Run(prompt="discover jobs", status=RunStatus.completed))
        s.add(Run(prompt="tailor cv", status=RunStatus.running))
        s.commit()
    r = client.get("/api/runs?limit=10")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 2
    assert {"id", "prompt", "status", "created_at"} <= set(rows[0].keys())
```

- [ ] **Step 2: Run → fail** (`/api/runs` list 404 — only `/{run_id}` exists).

- [ ] **Step 3: Add the list endpoint**

In `app/routers/runs.py`, add (BEFORE the `/{run_id}` route so the literal wins, and import `select`, `RunStatus` not needed):
```python
from sqlmodel import select  # add to imports


@router.get("")
def list_runs(limit: int = 30, session: Session = Depends(get_session)) -> list[dict]:
    rows = session.exec(
        select(Run).order_by(Run.created_at.desc()).limit(limit)
    ).all()
    return [
        {
            "id": r.id,
            "prompt": (r.prompt or "")[:140],
            "model": r.model,
            "status": r.status.value,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        }
        for r in rows
    ]
```
(Place the `@router.get("")` function above `get_run`.)

- [ ] **Step 4: Run test + gate** → PASS / GATE PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/routers/runs.py tests/test_runs_list.py
git commit -m "feat(runs): GET /api/runs list endpoint (recent agent runs)"
```

---

### Task 2: BoardInsightRail (resizable) + wire into BoardTab

**Files:** Modify `frontend/lib/api.ts`; Create `frontend/app/components/BoardInsightRail.tsx`; Modify `frontend/app/components/BoardTab.tsx`.

- [ ] **Step 1: api.ts — Run type + fetcher**

Add:
```ts
export type RunSummary = {
  id: string;
  prompt: string;
  model: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export async function fetchRuns(limit = 30): Promise<RunSummary[]> {
  const res = await fetch(`/api/runs?limit=${limit}`);
  if (!res.ok) throw new Error(`runs failed: ${res.status}`);
  return res.json();
}
```
(Verify `fetchAttention`, `fetchApplications`, `fetchOpportunities` already exist — they do.)

- [ ] **Step 2: Create `BoardInsightRail.tsx`**

A column that loads attention + runs + applications + opportunities and renders three sections. Use TwinForge/Job-Hunter tokens already in the app.
```tsx
"use client";

import { useEffect, useState } from "react";
import {
  Attention,
  RunSummary,
  Application,
  Opportunity,
  fetchAttention,
  fetchRuns,
  fetchApplications,
  fetchOpportunities,
} from "@/lib/api";

const ACTIVE = new Set(["active", "in_dialogue"]);

function timeAgo(iso: string): string {
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return `${Math.floor(d / 86400)}d ago`;
}

export default function BoardInsightRail({ onOpen }: { onOpen: (oppId: string) => void }) {
  const [att, setAtt] = useState<Attention | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [apps, setApps] = useState<Application[]>([]);
  const [opps, setOpps] = useState<Opportunity[]>([]);

  useEffect(() => {
    fetchAttention().then(setAtt).catch(() => setAtt(null));
    fetchRuns(12).then(setRuns).catch(() => setRuns([]));
    fetchApplications().then(setApps).catch(() => setApps([]));
    fetchOpportunities().then(setOpps).catch(() => setOpps([]));
  }, []);

  const decisions = (att?.items ?? []).filter(
    (i) => i.severity === "high" || i.kind === "untriaged_message"
  );
  const activeCount = opps.filter((o) => ACTIVE.has(o.stage)).length;

  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto bg-surface-alt p-5">
      {/* decisions */}
      <div>
        <div className="mb-3 flex items-center gap-2">
          <span className="text-[12px] font-bold uppercase tracking-wide text-ink-muted">Needs your decision</span>
          {decisions.length > 0 && (
            <span className="rounded-full bg-error px-1.5 text-[11px] font-bold text-white">{decisions.length}</span>
          )}
        </div>
        <div className="flex flex-col gap-2.5">
          {decisions.length === 0 ? (
            <div className="rounded-lg border border-ok-soft bg-ok-soft px-4 py-3 text-center text-[13px] font-semibold text-ok-deep">
              All caught up — automation has it from here.
            </div>
          ) : (
            decisions.slice(0, 6).map((d, i) => (
              <button
                key={i}
                onClick={() => d.opportunity_id && onOpen(d.opportunity_id)}
                className="rounded-xl border border-line bg-surface p-3 text-left transition hover:border-line-strong"
              >
                <div className="text-[13.5px] font-semibold leading-snug text-ink">{d.title}</div>
                <div className="mt-0.5 text-[12px] text-ink-muted">{d.reason}</div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* automation activity */}
      <div>
        <div className="mb-3 text-[12px] font-bold uppercase tracking-wide text-ink-muted">Automation activity</div>
        <div className="flex flex-col gap-3.5">
          {runs.length === 0 ? (
            <div className="text-[12.5px] text-ink-subtle">No recent runs.</div>
          ) : (
            runs.slice(0, 8).map((r) => (
              <div key={r.id} className="flex gap-2.5">
                <span className={`mt-1.5 h-2 w-2 flex-none rounded-full ${r.status === "completed" ? "bg-ok" : r.status === "failed" ? "bg-error" : "bg-accent"}`} />
                <div>
                  <div className="text-[12.5px] leading-snug text-ink-body">{r.prompt || "(agent run)"}</div>
                  <div className="font-mono text-[10px] text-ink-subtle">{r.status} · {timeAgo(r.created_at)}</div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* mini metrics (dark) */}
      <div className="rounded-xl bg-panel p-4 text-white">
        <div className="mb-3 text-[12px] font-bold uppercase tracking-wide text-white/60">Pipeline</div>
        <div className="flex gap-2.5">
          <div className="flex-1"><div className="text-[24px] font-bold leading-none">{apps.length}</div><div className="mt-1 text-[11px] text-white/55">Applied</div></div>
          <div className="flex-1"><div className="text-[24px] font-bold leading-none text-ok-mint">{activeCount}</div><div className="mt-1 text-[11px] text-white/55">Active</div></div>
          <div className="flex-1"><div className="text-[24px] font-bold leading-none">{decisions.length}</div><div className="mt-1 text-[11px] text-white/55">Decisions</div></div>
        </div>
      </div>
    </div>
  );
}
```
(If `Attention`/`Application`/`Opportunity` types lack a field used here — `items[].severity/kind/title/reason/opportunity_id`, `Opportunity.stage` — read `api.ts` and adjust to the real shape. The attention item shape comes from `needs_attention`.)

- [ ] **Step 3: Wire into BoardTab as a resizable split**

In `BoardTab.tsx`, import `BoardInsightRail` and `useState`/`useCallback` (already imported). Add rail-width state + a resize handler in the `BoardTab` component:
```tsx
const [railWidth, setRailWidth] = useState(340);
const startRailResize = useCallback((e: React.PointerEvent) => {
  e.preventDefault();
  const onMove = (ev: PointerEvent) => setRailWidth(Math.min(Math.max(window.innerWidth - ev.clientX, 260), 460));
  const onUp = () => {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
  };
  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
}, []);
```
Change the board body so the columns area and the rail sit in a row with a drag handle between them. Replace the columns wrapper region (the part from the `total === 0 ? … : <DndContext>…</DndContext>` down) so it is inside a `flex min-h-0 flex-1` row:
```tsx
<div className="flex min-h-0 flex-1">
  <div className="min-w-0 flex-1">
    {total === 0 ? (
      <p className="p-4 text-sm text-ink-muted">No opportunities in this view.</p>
    ) : (
      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        <div className="flex min-h-0 h-full gap-3 overflow-x-auto px-4 pb-4">
          {board.columns.map((stage) => (
            <Column key={stage} stage={stage} opps={board.by_stage[stage] ?? []} onOpen={onOpen} />
          ))}
        </div>
      </DndContext>
    )}
  </div>
  <div onPointerDown={startRailResize} className="w-1.5 flex-none cursor-col-resize border-l border-line hover:bg-accent/40" title="Drag to resize" />
  <div style={{ width: railWidth }} className="flex-none">
    <BoardInsightRail onOpen={onOpen} />
  </div>
</div>
```
Keep the filter pills + auto-discovery strip above this row exactly as they are.

- [ ] **Step 4: Build** — `npm --prefix frontend install` then `npm --prefix frontend run build` → succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/app/components/BoardInsightRail.tsx frontend/app/components/BoardTab.tsx
git commit -m "feat(ui): Board insight rail (decisions, activity, mini-metrics) — resizable"
```
