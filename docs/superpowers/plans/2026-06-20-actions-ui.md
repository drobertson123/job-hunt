# Actions / Tasks UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An Actions canvas tab (create form + filter + complete + click-through) over `/api/actions`, plus Done buttons in the Attention and Detail tabs.

**Architecture:** Frontend-only. `api.ts` gains `fetchActions`/`createAction`/`completeAction` (reusing the existing `Action` type); a new `ActionsTab` component; `page.tsx` adds the tab; `AttentionTab` and `OpportunityDetailTab` gain a Done button. The `/api/actions` list/create/complete endpoints already exist.

**Tech Stack:** Next.js (App Router static export), React 18, TypeScript, Tailwind.

## Global Constraints

- Frontend-only, additive. No backend/schema change (`/api/actions` list/create/complete already exist).
- No frontend test harness; per-task verification is `npm --prefix frontend run build` ("Compiled successfully", no type errors), run from the worktree root.
- Reuse the existing `Action` type and `fetch` idiom. Tab button styling copies the existing tab buttons verbatim.
- Components self-contained; do NOT add actions state to `page.tsx`. Leave the workspace block and other tabs (except the Done-button additions in Attention/Detail) unchanged.
- Action kinds: `followup, apply, research, prep, outreach, decision, other`. Complete is the only mutation beyond create.

---

### Task 1: api.ts — actions fetchers

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Produces: `fetchActions(status?: string, opportunityId?: string): Promise<Action[]>`; `createAction(body): Promise<Action>`; `completeAction(id: number): Promise<Action>`.

- [ ] **Step 1: Add the fetchers**

Append to `frontend/lib/api.ts` (the `Action` type already exists — do not redefine it):

```typescript
export async function fetchActions(status?: string, opportunityId?: string): Promise<Action[]> {
  const p = new URLSearchParams();
  if (status) p.set("status", status);
  if (opportunityId) p.set("opportunity_id", opportunityId);
  const qs = p.toString();
  const res = await fetch(`/api/actions${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`actions failed: ${res.status}`);
  return res.json();
}

export async function createAction(body: {
  title: string;
  kind?: string;
  detail?: string;
  due_at?: string | null;
  opportunity_id?: string | null;
}): Promise<Action> {
  const res = await fetch("/api/actions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`create action failed: ${res.status}`);
  return res.json();
}

export async function completeAction(id: number): Promise<Action> {
  const res = await fetch(`/api/actions/${id}/complete`, { method: "POST" });
  if (!res.ok) throw new Error(`complete action failed: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Verify it builds**

Run: `npm --prefix frontend run build`
Expected: "Compiled successfully", no type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(ui): actions fetchers (list/create/complete)"
```

---

### Task 2: ActionsTab component + page wiring

**Files:**
- Create: `frontend/app/components/ActionsTab.tsx`
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `fetchActions`/`createAction`/`completeAction` (Task 1); `fetchOpportunities`, `Action`, `Opportunity`; existing `selectedOpp`/`setSelectedOpp`/`setCanvasTab`.
- Produces: `<ActionsTab onOpen={(oppId: string) => void} />`.

- [ ] **Step 1: Create `frontend/app/components/ActionsTab.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Action,
  Opportunity,
  completeAction,
  createAction,
  fetchActions,
  fetchOpportunities,
} from "@/lib/api";

type Filter = "open" | "done" | "all";
const KINDS = ["followup", "apply", "research", "prep", "outreach", "decision", "other"];

export default function ActionsTab({ onOpen }: { onOpen: (oppId: string) => void }) {
  const [actions, setActions] = useState<Action[]>([]);
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [filter, setFilter] = useState<Filter>("open");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("other");
  const [dueAt, setDueAt] = useState("");
  const [oppId, setOppId] = useState("");

  const load = useCallback(() => {
    fetchActions(filter === "all" ? undefined : filter)
      .then(setActions)
      .catch(() => setActions([]));
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    fetchOpportunities().then(setOpps).catch(() => setOpps([]));
  }, []);

  const submit = async () => {
    if (!title.trim()) return;
    await createAction({
      title: title.trim(),
      kind,
      due_at: dueAt || null,
      opportunity_id: oppId || null,
    });
    setTitle("");
    setDueAt("");
    setOppId("");
    setKind("other");
    load();
  };

  const titleFor = (id: string | null) =>
    id ? opps.find((o) => o.id === id)?.title ?? id : null;

  return (
    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 text-sm">
      <div className="flex flex-wrap items-center gap-2 rounded border border-slate-200 p-2">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="New action…"
          className="flex-1 rounded border px-2 py-1 text-sm"
        />
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          className="rounded border px-1 py-1 text-xs"
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <input
          type="date"
          value={dueAt}
          onChange={(e) => setDueAt(e.target.value)}
          className="rounded border px-1 py-1 text-xs"
        />
        <select
          value={oppId}
          onChange={(e) => setOppId(e.target.value)}
          className="rounded border px-1 py-1 text-xs"
        >
          <option value="">— no opportunity —</option>
          {opps.map((o) => (
            <option key={o.id} value={o.id}>
              {o.title}
            </option>
          ))}
        </select>
        <button
          onClick={submit}
          disabled={!title.trim()}
          className="rounded bg-slate-900 px-3 py-1 text-xs text-white disabled:opacity-50"
        >
          Add
        </button>
      </div>

      <div className="flex gap-1">
        {(["open", "done", "all"] as Filter[]).map((f) => (
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

      {actions.length === 0 ? (
        <p className="text-slate-400">No actions.</p>
      ) : (
        actions.map((a) => {
          const t = titleFor(a.opportunity_id);
          const past =
            a.due_at && a.status === "open" && new Date(a.due_at) < new Date();
          return (
            <div
              key={a.id}
              className="flex items-center gap-2 rounded border border-slate-200 p-2"
            >
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs uppercase text-slate-600">
                {a.kind}
              </span>
              <span className="flex-1">{a.title}</span>
              {t && (
                <span
                  onClick={() => onOpen(a.opportunity_id as string)}
                  className="cursor-pointer text-xs text-blue-600 hover:underline"
                >
                  {t}
                </span>
              )}
              {a.due_at && (
                <span className={`text-xs ${past ? "text-red-600" : "text-slate-500"}`}>
                  {new Date(a.due_at).toLocaleDateString()}
                </span>
              )}
              {a.status === "open" ? (
                <button
                  onClick={() => completeAction(a.id).then(load)}
                  className="rounded bg-slate-200 px-2 py-0.5 text-xs hover:bg-slate-300"
                >
                  Done
                </button>
              ) : (
                <span className="text-xs text-slate-400">{a.status}</span>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
```

- [ ] **Step 2: Wire into `frontend/app/page.tsx`**

Read `page.tsx` first. Then:
1. Import: `import ActionsTab from "./components/ActionsTab";`
2. Widen the `canvasTab` union (the existing multi-line `useState`) to add `"actions"`.
3. Add an "Actions" tab button after the Companies button (verbatim style — copy the exact className expression, substituting `"actions"`):
```tsx
            <button
              className={`border-b-2 py-2 ${
                canvasTab === "actions"
                  ? "border-slate-900 text-slate-900"
                  : "border-transparent text-slate-400 hover:text-slate-600"
              }`}
              onClick={() => setCanvasTab("actions")}
            >
              Actions
            </button>
```
4. Add a render branch before the final workspace `) : (`:
```tsx
          ) : canvasTab === "actions" ? (
            <ActionsTab
              onOpen={(id) => {
                setSelectedOpp(id);
                setCanvasTab("detail");
              }}
            />
```

Do NOT add actions state to `page.tsx`; leave the workspace block and other tabs unchanged.

- [ ] **Step 3: Verify it builds**

Run: `npm --prefix frontend run build`
Expected: "Compiled successfully", no type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/ActionsTab.tsx frontend/app/page.tsx
git commit -m "feat(ui): Actions canvas tab (create + filter + complete)"
```

---

### Task 3: Done buttons in Attention + Detail

**Files:**
- Modify: `frontend/app/components/AttentionTab.tsx`
- Modify: `frontend/app/components/OpportunityDetailTab.tsx`

**Interfaces:**
- Consumes: `completeAction` (Task 1).

- [ ] **Step 1: AttentionTab — refactor fetch into `load` + Done button**

Read `frontend/app/components/AttentionTab.tsx`.

1. Update the imports:
```tsx
import { useCallback, useEffect, useState } from "react";
import { Attention, AttentionItem, completeAction, fetchAttention } from "@/lib/api";
```
2. Replace the existing one-time fetch:
```tsx
  const [data, setData] = useState<Attention | null>(null);

  useEffect(() => {
    fetchAttention().then(setData).catch(() => setData(null));
  }, []);
```
with a reusable `load`:
```tsx
  const [data, setData] = useState<Attention | null>(null);

  const load = useCallback(() => {
    fetchAttention().then(setData).catch(() => setData(null));
  }, []);

  useEffect(() => {
    load();
  }, [load]);
```
3. The item rows are rendered by a `Row` component (`function Row({ item, onOpen })`). Add an `onComplete` prop and a Done button shown only for `overdue_action` items that have an `action_id`. Update the `Row` signature and body:
```tsx
function Row({
  item,
  onOpen,
  onComplete,
}: {
  item: AttentionItem;
  onOpen: (id: string) => void;
  onComplete: () => void;
}) {
```
Inside the row JSX, after the text block, add (so a Done click does not also trigger the row's `onOpen`):
```tsx
      {item.kind === "overdue_action" && item.action_id != null && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            completeAction(item.action_id as number).then(onComplete);
          }}
          className="ml-auto rounded bg-slate-200 px-2 py-0.5 text-xs hover:bg-slate-300"
        >
          Done
        </button>
      )}
```
4. At the `Row` call site (inside the groups `.map`), pass `onComplete={load}`:
```tsx
              <Row key={...} item={item} onOpen={onOpen} onComplete={load} />
```
(Keep the existing `key`. Read the real call site and add only the `onComplete` prop.)

- [ ] **Step 2: OpportunityDetailTab — Done button in the Actions section**

Read `frontend/app/components/OpportunityDetailTab.tsx`. Add `completeAction` to the `@/lib/api` import. In the Actions section row (currently renders `<Badge>{a.status}</Badge>`, title, kind, due), add a Done button when `a.status === "open"`, calling `load` (the tab's existing `useCallback`):

```tsx
            {a.status === "open" && (
              <button
                onClick={() => completeAction(a.id).then(load)}
                className="ml-auto rounded bg-slate-200 px-2 py-0.5 text-xs hover:bg-slate-300"
              >
                Done
              </button>
            )}
```
(Place it inside the action row `div`, after the due-date span. Read the real markup first to match it.)

- [ ] **Step 3: Verify build + full backend suite + gate**

Run: `npm --prefix frontend run build`
Expected: "Compiled successfully", no type errors.
Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all — no backend change).
Run: `scripts/ci/gate.sh`
Expected: GATE PASSED.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/AttentionTab.tsx frontend/app/components/OpportunityDetailTab.tsx
git commit -m "feat(ui): complete actions from Attention + Detail tabs"
```

---

## Final verification

- [ ] `npm --prefix frontend run build` → Compiled successfully.
- [ ] `scripts/ci/gate.sh` → GATE PASSED.
- [ ] `git log --oneline` shows 3 focused commits on `feature/actions-ui`.

## Self-Review (completed by plan author)

- **Spec coverage:** fetchers (T1, spec §3); ActionsTab create-form/filter/list/complete/click-through + page wiring (T2, §4–5); Attention `load` refactor + Done on overdue_action, Detail Done on open actions (T3, §6); build verification (§7).
- **Placeholder scan:** none — full ActionsTab code; cross-component edits give the exact JSX and reference the real `Row`/Actions-section markup (implementer reads the files first).
- **Type consistency:** `fetchActions`/`createAction`/`completeAction` signatures identical across T1 def and T2/T3 use. `Action` fields (`id`, `title`, `kind`, `status`, `due_at`, `opportunity_id`) match the existing type. `AttentionItem.action_id` is `number | undefined` on the existing loose type; the `item.action_id != null` guard + `as number` cast is sound. `completeAction(id: number)` matches `a.id`/`item.action_id` (both numeric). `onComplete: () => void` = `load`.
