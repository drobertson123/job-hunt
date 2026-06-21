# Attention Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only "Attention" canvas tab showing the `GET /api/attention` counts + grouped items (overdue actions / stale opps / untriaged), with click-through to an opportunity's Detail tab.

**Architecture:** Frontend-only. `api.ts` gains `Attention`/`AttentionItem` types + `fetchAttention`; a self-contained `AttentionTab` component renders the dashboard; `page.tsx` adds a tab keyed to the existing `selectedOpp`/`setCanvasTab`. Zero backend changes (`/api/attention` already exists).

**Tech Stack:** Next.js (App Router static export), React 18, TypeScript, Tailwind.

## Global Constraints

- Frontend-only, additive, READ-ONLY: no complete/snooze/write actions; no routing; no backend/schema change.
- No frontend test harness; per-task verification is `npm --prefix frontend run build` ("Compiled successfully", no type errors), run from the worktree root.
- Reuse the exact `fetch` idiom already in `frontend/lib/api.ts` (throw on `!res.ok`, return `res.json()`).
- Tab button styling copies the existing tab buttons verbatim (`` className={`border-b-2 py-2 ${canvasTab === "X" ? "border-slate-900 text-slate-900" : "border-transparent text-slate-400 hover:text-slate-600"}`} ``).
- Component is self-contained; do NOT add attention state to `page.tsx`. Leave the workspace block and other tabs unchanged.
- Click-through only for items with a non-null `opportunity_id`.

---

### Task 1: api.ts — attention types + fetcher

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Produces: `AttentionItem`, `Attention` types; `fetchAttention(): Promise<Attention>`.

- [ ] **Step 1: Add the types + fetcher**

Append to `frontend/lib/api.ts`:

```typescript
export type AttentionItem = {
  kind: string; // "overdue_action" | "stale_opportunity" | "untriaged_opportunity"
  severity: string; // "high" | "medium" | ...
  opportunity_id: string | null;
  title: string;
  reason: string;
  action_id?: number;
  due_at?: string | null;
  stage?: string;
  last_activity_at?: string;
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

- [ ] **Step 2: Verify it builds**

Run: `npm --prefix frontend run build`
Expected: "Compiled successfully", no type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(ui): attention types + fetchAttention"
```

---

### Task 2: AttentionTab component + page wiring

**Files:**
- Create: `frontend/app/components/AttentionTab.tsx`
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `Attention`, `AttentionItem`, `fetchAttention` (Task 1); existing `selectedOpp`/`setSelectedOpp`/`setCanvasTab` in `page.tsx`.
- Produces: `<AttentionTab onOpen={(oppId: string) => void} />`.

- [ ] **Step 1: Create `frontend/app/components/AttentionTab.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { Attention, AttentionItem, fetchAttention } from "@/lib/api";

const GROUPS: { kind: string; label: string }[] = [
  { kind: "overdue_action", label: "Overdue actions" },
  { kind: "stale_opportunity", label: "Stale opportunities" },
  { kind: "untriaged_opportunity", label: "Untriaged opportunities" },
];

function sevColor(severity: string): string {
  if (severity === "high") return "bg-red-500";
  if (severity === "medium") return "bg-amber-500";
  return "bg-slate-400";
}

function itemDetail(item: AttentionItem): string | null {
  if (item.kind === "overdue_action" && item.due_at) {
    return `due ${new Date(item.due_at).toLocaleDateString()}`;
  }
  if (item.kind === "stale_opportunity") {
    const when = item.last_activity_at
      ? ` · last activity ${new Date(item.last_activity_at).toLocaleDateString()}`
      : "";
    return `${item.stage ?? ""}${when}`;
  }
  if (item.kind === "untriaged_opportunity") {
    return item.stage ?? null;
  }
  return null;
}

function Row({ item, onOpen }: { item: AttentionItem; onOpen: (id: string) => void }) {
  const clickable = item.opportunity_id != null;
  const detail = itemDetail(item);
  return (
    <div
      onClick={clickable ? () => onOpen(item.opportunity_id as string) : undefined}
      className={`flex items-start gap-2 rounded border border-slate-200 p-2 text-sm ${
        clickable ? "cursor-pointer hover:bg-slate-50" : ""
      }`}
    >
      <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${sevColor(item.severity)}`} />
      <div className="flex flex-col">
        <span className="font-medium">{item.title}</span>
        <span className="text-xs text-slate-500">{item.reason}</span>
        {detail && <span className="text-xs text-slate-400">{detail}</span>}
      </div>
    </div>
  );
}

export default function AttentionTab({ onOpen }: { onOpen: (oppId: string) => void }) {
  const [data, setData] = useState<Attention | null>(null);

  useEffect(() => {
    fetchAttention().then(setData).catch(() => setData(null));
  }, []);

  if (!data) {
    return <p className="p-4 text-sm text-slate-400">Loading…</p>;
  }
  if (data.counts.total === 0) {
    return <p className="p-4 text-sm text-slate-400">Nothing needs attention 🎉</p>;
  }

  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="rounded bg-red-100 px-2 py-0.5 text-red-700">
          Overdue {data.counts.overdue_actions}
        </span>
        <span className="rounded bg-amber-100 px-2 py-0.5 text-amber-700">
          Stale {data.counts.stale_opportunities}
        </span>
        <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600">
          Untriaged {data.counts.untriaged_opportunities}
        </span>
        <span className="rounded bg-slate-900 px-2 py-0.5 text-white">
          Total {data.counts.total}
        </span>
      </div>

      {GROUPS.map(({ kind, label }) => {
        const rows = data.items.filter((i) => i.kind === kind);
        if (rows.length === 0) return null;
        return (
          <div key={kind} className="flex flex-col gap-1">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {label} ({rows.length})
            </h3>
            {rows.map((item, i) => (
              <Row
                key={item.action_id ?? item.opportunity_id ?? `${kind}-${i}`}
                item={item}
                onOpen={onOpen}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Wire into `frontend/app/page.tsx`**

Read `frontend/app/page.tsx` first. Then:

1. Add the import beside the other component imports:
```tsx
import AttentionTab from "./components/AttentionTab";
```
2. Widen the `canvasTab` union (the existing multi-line `useState`) to add `"attention"`:
```tsx
  const [canvasTab, setCanvasTab] = useState<
    "workspace" | "profile" | "applications" | "briefing" | "detail" | "board" | "attention"
  >("workspace");
```
3. Add an "Attention" tab button after the Board button (verbatim style — copy the exact className expression from an existing button, substituting `"attention"`):
```tsx
            <button
              className={`border-b-2 py-2 ${
                canvasTab === "attention"
                  ? "border-slate-900 text-slate-900"
                  : "border-transparent text-slate-400 hover:text-slate-600"
              }`}
              onClick={() => setCanvasTab("attention")}
            >
              Attention
            </button>
```
4. Add a render branch in the ternary chain, before the final workspace `) : (`:
```tsx
          ) : canvasTab === "attention" ? (
            <AttentionTab
              onOpen={(id) => {
                setSelectedOpp(id);
                setCanvasTab("detail");
              }}
            />
```

Do NOT add attention state to `page.tsx`; leave the workspace block and other tabs unchanged.

- [ ] **Step 3: Verify it builds**

Run: `npm --prefix frontend run build`
Expected: "Compiled successfully", no type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/AttentionTab.tsx frontend/app/page.tsx
git commit -m "feat(ui): read-only Attention canvas tab"
```

---

## Final verification

- [ ] `npm --prefix frontend run build` → Compiled successfully.
- [ ] `scripts/ci/gate.sh` → GATE PASSED (backend suite unaffected; confirms no regression).
- [ ] `git log --oneline` shows 2 focused commits on `feature/attention-dashboard`.

## Self-Review (completed by plan author)

- **Spec coverage:** attention types + fetcher (T1, spec §3); component counts summary, empty state, grouped items with severity dot + kind-specific detail, click-through only for non-null `opportunity_id`, keys via action_id/opportunity_id/index (T2, §4); page wiring with `setSelectedOpp`+`setCanvasTab("detail")`, no attention state in page.tsx (T2, §5); build-only verification (both tasks, §6).
- **Placeholder scan:** none — full component code; page.tsx edits give verbatim button/branch code.
- **Type consistency:** `fetchAttention(): Promise<Attention>` used in T2; `AttentionItem` optional fields (`action_id`, `due_at`, `stage`, `last_activity_at`) read in `itemDetail`/keys match the type def; `onOpen` signature matches between T2 prop and the page caller; counts field names (`overdue_actions`/`stale_opportunities`/`untriaged_opportunities`/`total`) match the backend `needs_attention` return.
