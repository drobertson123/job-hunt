# Tab Count Badges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax.

**Goal:** Show counts on the Board / Attention / Companies / Actions tab labels.

**Architecture:** Frontend-only edit to `frontend/app/page.tsx` — extend `refreshCanvas`'s `Promise.all` with attention/companies/open-actions fetches, store counts, render in labels.

## Global Constraints
- No backend change. Verify with `npm --prefix frontend run build`.
- Reuse existing `fetchAttention`/`fetchCompanies`/`fetchActions` from `@/lib/api`.
- Keep all existing `refreshCanvas` behavior; only add to it.

---

### Task 1: Counts in page.tsx

**Files:** Modify `frontend/app/page.tsx`.

- [ ] **Step 1: Wire counts**

READ `frontend/app/page.tsx` first. Then:
1. Add to the `@/lib/api` import: `fetchAttention`, `fetchCompanies`, `fetchActions`.
2. Add three state numbers near the other `useState`s:
```tsx
  const [attentionCount, setAttentionCount] = useState(0);
  const [companyCount, setCompanyCount] = useState(0);
  const [openActionCount, setOpenActionCount] = useState(0);
```
3. In `refreshCanvas`'s `Promise.all([...])`, append `fetchAttention()`, `fetchCompanies()`, `fetchActions("open")` to the array and destructure them (e.g. `const [n, a, o, apps, att, companies, openActions] = await Promise.all([...]);`). After the existing setters add:
```tsx
      setAttentionCount(att.counts.total);
      setCompanyCount(companies.length);
      setOpenActionCount(openActions.length);
```
(Keep the existing `setNotes(n)`/`setArtifacts(a)`/`setOpps(o)`/`setApplications(apps)` exactly. The whole block is already in a try/catch — extend it.)
4. Update the four tab-button labels (currently `Board`, `Attention`, `Companies`, `Actions` with no count):
   - `Board ({opps.length})`
   - `Attention ({attentionCount})`
   - `Companies ({companyCount})`
   - `Actions ({openActionCount})`
   Match the surrounding label markup (the existing `Applications ({applications.length})` button shows the convention).

- [ ] **Step 2: Verify** — `npm --prefix frontend run build` (Compiled successfully); `.venv/bin/python -m pytest -q`; `./scripts/ci/gate.sh`. (Worktree may need `npm --prefix frontend install` first.)
- [ ] **Step 3: Commit** — `git add frontend/app/page.tsx && git commit -m "feat(ui): count badges on Board/Attention/Companies/Actions tabs"`

---

## Final verification
- [ ] `npm --prefix frontend run build` OK; `scripts/ci/gate.sh` PASSED; 1 commit on `feature/ui-tab-counts`.

## Self-Review
- Spec coverage: 3 count states + 3 fetches in refreshCanvas + 4 label updates (T1). `fetchAttention` returns `{items, counts:{total}}`; `fetchCompanies`/`fetchActions` return arrays. Board uses existing `opps`. No backend change, no placeholders.
