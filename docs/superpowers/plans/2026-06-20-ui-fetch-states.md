# Consistent Fetch States Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add a shared `FetchError` (Retry) component and an `error` state to 7 canvas tabs so a failed fetch shows "Couldn't load — Retry" instead of "Loading…" forever.

**Architecture:** Frontend-only, uniform per-tab transform. New `FetchError.tsx`; each tab gains an `error` boolean (set in `.catch`, cleared on success) and short-circuits to `<FetchError onRetry={load} />`. Bare-`useEffect` fetches are refactored to a `load` `useCallback`.

**Tech Stack:** Next.js, React, TypeScript, Tailwind.

## Global Constraints

- No backend change. Verify each task with `npm --prefix frontend run build` (Compiled successfully).
- Uniform transform per component: add `error` state; in the fetch use `.then(d => { setX(d); setError(false); })` + `.catch(() => { setX(<existing-empty>); setError(true); })`; ensure a `load` `useCallback`; render `if (error) return <FetchError onRetry={load} />;` BEFORE the existing loading/empty checks; import `FetchError`.
- Keep each component's existing loading/empty/data rendering; only add the error branch (and refactor to `load` if the fetch was inline in `useEffect`).
- `<FetchError />` is shared at `frontend/app/components/FetchError.tsx`.

---

### Task 1: FetchError component + 4 tabs

**Files:** Create `frontend/app/components/FetchError.tsx`; Modify `ApplicationsTab.tsx`, `BriefingTab.tsx`, `ActionsTab.tsx`, `CompaniesTab.tsx`.

- [ ] **Step 1: Create `frontend/app/components/FetchError.tsx`**

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

- [ ] **Step 2: Apply the transform to each of the 4 tabs**

For `ApplicationsTab.tsx`, `BriefingTab.tsx`, `ActionsTab.tsx`, `CompaniesTab.tsx` — READ EACH FILE FIRST, then:
1. Import `FetchError` (`import FetchError from "./FetchError";`).
2. Add `const [error, setError] = useState(false);`.
3. Ensure a `load`/refetch `useCallback` exists (ActionsTab and CompaniesTab already have `load`; ApplicationsTab/BriefingTab fetch in `useEffect` — wrap that fetch in a `const load = useCallback(() => {...}, [deps])` and call it from `useEffect(() => { load(); }, [load])`, preserving the current dep behavior, e.g. BriefingTab depends on `opportunityId`).
4. In the fetch's `.then`, also `setError(false)`; change the `.catch(() => setX(...))` to `.catch(() => { setX(<the same empty value used today: null or [])>); setError(true); })`.
5. At the top of the rendered output, before the existing "no data"/loading/empty return, add: `if (error) return <FetchError onRetry={load} />;`. (For a tab whose top guard is `if (!data) return <Loading/>`, place the `error` check immediately before it. For a tab with no early loading return — e.g. one that maps an array — add the `error` check at the very top of the returned JSX function body before the main `return`.)

Match each file's real fetch/handlers; don't change unrelated behavior. For BriefingTab, keep the synthesize button working (its own busy state is separate from `error`).

- [ ] **Step 3: Verify** — `npm --prefix frontend run build` (Compiled successfully).
- [ ] **Step 4: Commit** — `git add frontend/app/components/FetchError.tsx frontend/app/components/ApplicationsTab.tsx frontend/app/components/BriefingTab.tsx frontend/app/components/ActionsTab.tsx frontend/app/components/CompaniesTab.tsx && git commit -m "feat(ui): FetchError + error states (Applications/Briefing/Actions/Companies)"`

---

### Task 2: 3 remaining tabs

**Files:** Modify `BoardTab.tsx`, `AttentionTab.tsx`, `OpportunityDetailTab.tsx`.

- [ ] **Step 1: Apply the same transform**

For `BoardTab.tsx`, `AttentionTab.tsx`, `OpportunityDetailTab.tsx` — READ EACH FIRST — apply steps 1–5 from Task 1 (import `FetchError`, add `error` state, set/clear it in the `load` fetch's then/catch, render `if (error) return <FetchError onRetry={load} />;` before the existing loading guard). All three already have a `load` `useCallback`.

Notes:
- `OpportunityDetailTab`/`BoardTab`/`AttentionTab` already early-return on `!data`/`!board`/`!detail`; put the `error` check just before that.
- `OpportunityDetailTab.load` no-ops when `opportunityId` is empty — keep that; the error check only matters when a fetch was attempted.

- [ ] **Step 2: Verify** — `npm --prefix frontend run build` (Compiled successfully); then `.venv/bin/python -m pytest -q` and `./scripts/ci/gate.sh` (no backend change — confirms no regression).
- [ ] **Step 3: Commit** — `git add frontend/app/components/BoardTab.tsx frontend/app/components/AttentionTab.tsx frontend/app/components/OpportunityDetailTab.tsx && git commit -m "feat(ui): error states in Board/Attention/Detail tabs"`

---

## Final verification
- [ ] `npm --prefix frontend run build` OK; `scripts/ci/gate.sh` PASSED; 2 commits on `feature/ui-fetch-states`.

## Self-Review
- Spec coverage: FetchError + 4 tabs (T1), 3 tabs (T2) = all 7. Uniform transform. No placeholders beyond the intentional "read each file and apply the pattern" (the fetch lines differ per component; the transform is explicit). No backend change.
