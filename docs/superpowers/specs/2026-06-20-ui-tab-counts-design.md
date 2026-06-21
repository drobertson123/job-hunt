# Design: Tab Count Badges

**Date:** 2026-06-20
**Status:** Approved (autonomous goal) — UI improvement

## 1. Purpose

Most canvas tabs show no count, so you can't see at a glance how many
opportunities are on the board, items need attention, companies exist, or tasks
are open. Add counts to the **Board / Attention / Companies / Actions** tab
labels (Applications already shows one; Workspace shows artifact/note counts).

## 2. Scope

Frontend-only, in `frontend/app/page.tsx`. Extend the existing `refreshCanvas`
`Promise.all` to also fetch attention, companies, and open actions; store three
count numbers; render them in the tab labels. Board uses the already-fetched
`opps.length`.

**Out of scope:** Briefing/Detail counts (per-selection, not a single number);
a backend counts endpoint (reuse existing list/attention endpoints); badge
styling beyond the existing `(N)` label convention. No backend change.

## 3. `frontend/app/page.tsx`

- Add three state numbers: `attentionCount`, `companyCount`, `openActionCount`
  (default 0).
- Add `fetchAttention`, `fetchCompanies`, `fetchActions` to the `@/lib/api`
  import.
- In `refreshCanvas`'s `Promise.all`, add `fetchAttention()`,
  `fetchCompanies()`, `fetchActions("open")`; from the results set
  `setAttentionCount(att.counts.total)`, `setCompanyCount(companies.length)`,
  `setOpenActionCount(openActions.length)`. Keep the existing
  notes/artifacts/opportunities/applications handling. The whole `Promise.all`
  is already wrapped in the existing try/catch — extend it; on error the counts
  stay at their last value (acceptable).
- Update the four tab-button labels:
  - `Board ({opps.length})`
  - `Attention ({attentionCount})`
  - `Companies ({companyCount})`
  - `Actions ({openActionCount})`

## 4. Testing

Frontend-only; verified via `npm --prefix frontend run build`. No backend change;
the plan's final step runs `scripts/ci/gate.sh` to confirm no regression.

## 5. Notes

- `refreshCanvas` already re-runs on agent `tool_result`/`result` events, so the
  counts update live as the agent writes data.
- `fetchActions("open")` returns only open actions; its length is the open-task
  count.
