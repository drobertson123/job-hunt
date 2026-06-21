# Design: Actions / Tasks UI

**Date:** 2026-06-20
**Status:** Approved design — ready for implementation plan

## 1. Purpose

Surface the actions/tasks backend (`/api/actions`) in the UI so the user can
see, create, and complete next-steps — turning the app from a viewer into
something that drives daily work. Also makes the existing Attention and Detail
tabs actionable (complete an action where you see it). `/api/actions` already
has list/create/complete; no backend change.

## 2. Scope

Frontend-only: a new "Actions" canvas tab (create form + filterable list +
complete + click-through), plus Done buttons wired into the Attention tab's
overdue-action items and the Detail tab's Actions section.

**Out of scope:** edit/delete/snooze/reopen actions; recurring tasks; due-time
(date only); any backend change. Follows existing component/`api.ts` patterns.

## 3. `frontend/lib/api.ts`

Reuses the existing `Action` type (`id, title, detail, kind, status, due_at,
opportunity_id`).

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

(The backend `due_at` accepts an ISO datetime; a date-only `"YYYY-MM-DD"` from an
`<input type="date">` parses to midnight server-side. Send `null`/omit when empty.)

## 4. `frontend/app/components/ActionsTab.tsx`

Props: `{ onOpen: (oppId: string) => void }`.

State: `actions: Action[]`, `opps: Opportunity[]` (for the create dropdown + title
lookup), `filter: "open" | "done" | "all"` (default `"open"`), and controlled
create-form fields (`title`, `kind`, `dueAt`, `oppId`).

- **Load** (`useCallback`, dep `[filter]`): `fetchActions(filter === "all" ?
  undefined : filter)` → set; also `fetchOpportunities()` once for the dropdown.
- **Create form** (a small row): title `<input>` (required), kind `<select>`
  (followup/apply/research/prep/outreach/decision/other), due `<input type=date>`,
  opportunity `<select>` (optional; "— none —" default). On submit: guard
  non-empty title → `createAction({title, kind, due_at: dueAt || null,
  opportunity_id: oppId || null})` → reload + clear fields.
- **Filter** segmented control: Open / Done / All.
- **List:** each row — a kind badge, the title, the opportunity title (looked up
  from `opps` by `opportunity_id`, clickable → `onOpen`), due date (red when past
  and status open), and a **Done** button when `status === "open"` →
  `completeAction(id)` → reload. Empty state when no actions.

## 5. `frontend/app/page.tsx`

- Import `ActionsTab`.
- Widen the `canvasTab` union with `"actions"`.
- Add an "Actions" tab button styled like the others.
- Render `<ActionsTab onOpen={(id) => { setSelectedOpp(id); setCanvasTab("detail"); }} />`.
- No actions state in `page.tsx`; other tabs/workspace unchanged.

## 6. Cross-component complete

- **`AttentionTab`**: refactor its one-time `useEffect(fetchAttention)` into a
  `load` `useCallback` + `useEffect([load])`. On `overdue_action` items (which
  carry `action_id`), render a **Done** button → `completeAction(item.action_id)`
  → `load()`. Import `completeAction`. (Other item kinds have no `action_id` and
  get no button.)
- **`OpportunityDetailTab`**: in the Actions section row, when `a.status ===
  "open"`, render a **Done** button → `completeAction(a.id)` → `load()` (the tab
  already has a `load` `useCallback`). Import `completeAction`.

## 7. Testing

Frontend-only; no frontend test harness, none added. Verification is
`npm --prefix frontend run build` ("Compiled successfully", no type errors).
Backend pytest suite untouched; the plan's final step runs `scripts/ci/gate.sh`
to confirm no regression.

## 8. Notes

- This is the first UI with a create form (a write path beyond board-drag and
  company backfill); the API already validates (`title` required).
- `AttentionItem.action_id` is already on the loose `AttentionItem` type (used by
  the overdue-followup work); no type change needed there.
- Completing an action server-side sets `status=done` + `completed_at`; the
  Attention/Detail/Actions views reload to reflect it.
