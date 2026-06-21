# Design: Consistent Fetch States (loading / error+Retry)

**Date:** 2026-06-20
**Status:** Approved (autonomous goal) — UI improvement

## 1. Purpose

Seven canvas tabs (`ApplicationsTab`, `BriefingTab`, `CompaniesTab`,
`ActionsTab`, `OpportunityDetailTab`, `BoardTab`, `AttentionTab`) collapse a
fetch error into `setData(null)` and render **"Loading…" forever** on failure —
the user can't tell loading from broken and has no way to recover. Add a
consistent **error state with a Retry button** across them.

## 2. Scope

Frontend-only. A shared `FetchError` component + an `error` state per tab (set in
`.catch`, cleared on success), rendered before the existing loading/empty
states. Tabs whose fetch lives in a bare `useEffect` are refactored to a `load`
`useCallback` so Retry can re-invoke it.

**Out of scope:** count badges; visual redesign; a generic data-fetching hook
(keep per-component fetch logic; just add the error branch). No backend change.

## 3. Shared component — `frontend/app/components/FetchError.tsx`

```tsx
"use client";

export default function FetchError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="p-4 text-sm text-slate-500">
      Couldn’t load.{" "}
      <button onClick={onRetry} className="text-blue-600 underline">
        Retry
      </button>
    </div>
  );
}
```

## 4. Per-tab change (uniform)

For each of the 7 components:
- Add `const [error, setError] = useState(false)`.
- Ensure the fetch is in a `load` `useCallback` (refactor a bare `useEffect`
  fetch into `const load = useCallback(() => {...}, [deps])` + `useEffect(() => { load(); }, [load])`). Some already have `load` (Detail, Board, Attention, Actions, Companies); add to those that don't.
- In the fetch: `.then((d) => { setX(d); setError(false); })` and
  `.catch(() => { setX(<null/[]>); setError(true); })`.
- At the top of render, before the loading/empty checks:
  `if (error) return <FetchError onRetry={load} />;`
- Import `FetchError`.

The existing "Loading…" / empty-state lines stay (they now only show during a
genuine in-flight or empty state, not on error).

## 5. Testing

Frontend-only; verified via `npm --prefix frontend run build`. No backend change
(suite unaffected; the plan's final step runs `scripts/ci/gate.sh` to confirm).

## 6. Notes

- Tabs that take a `load` from a parent or fetch on `opportunityId` change keep
  their dep array; Retry re-runs the current `load`.
- This is the first shared presentational component extracted across tabs — a
  small, justified DRY step (the error block is identical everywhere).
