# Opportunity Detail Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Rebuild `OpportunityDetailTab` to the Job Hunter design — logo+title header with a fit pill, a clickable stage stepper, and a two-column card layout — while preserving ALL existing functionality.

## Global Constraints
- PRESERVE every functional piece currently in `OpportunityDetailTab`: the data fetch (`fetchOpportunityDetail`), all sections (briefing, applications, contacts + the add-contact form, communications, actions + `completeAction`, artifacts, decisions, company, source), and any handlers (`createContact`, `completeAction`). Restyle/relayout only — do not drop features.
- Use the app's design tokens (warm/purple Job Hunter palette): cards = `rounded-xl border border-line bg-surface p-5`; section labels = `text-[12.5px] font-bold uppercase tracking-wide text-ink-subtle`; body text `text-ink-body`; muted `text-ink-muted`.
- Frontend: `npm --prefix frontend install` then `npm --prefix frontend run build` → succeeds.
- Do NOT invoke any finishing/branch skill — stop after committing.

---

### Task 1: Rebuild the detail layout

**Files:** Modify `frontend/app/components/OpportunityDetailTab.tsx`, `frontend/app/page.tsx` (pass `onBack`).

- [ ] **Step 1: Add a Back affordance**

In `page.tsx`, where `<OpportunityDetailTab opportunityId={…} />` is rendered (the `canvasTab === "detail"` branch), pass `onBack={() => setCanvasTab("board")}`. Update the component's props to `{ opportunityId: string; onBack?: () => void }`.

- [ ] **Step 2: Rebuild the component**

READ the current `OpportunityDetailTab.tsx` fully first. Keep its state, `load`/fetch, the add-contact form state+submit, and `completeAction` calls. Replace the RENDER with this structure (map the existing data into it; keep the FetchError/loading guards):

Header (after a Back button `← Back to board` calling `onBack`):
```tsx
<div className="mb-2 flex items-start gap-4">
  <div className="flex h-12 w-12 flex-none items-center justify-center rounded-lg bg-accent-tint text-[15px] font-bold text-accent">
    {(o.organization || o.title).slice(0, 2).toUpperCase()}
  </div>
  <div className="min-w-0 flex-1">
    <div className="flex flex-wrap items-center gap-2.5">
      <h1 className="m-0 text-[23px] font-bold tracking-tight text-ink">{o.title}</h1>
      {o.fit_score != null && (
        <span className="rounded-md bg-accent-tint px-2 py-0.5 text-[11.5px] font-semibold text-accent">Fit {o.fit_score}</span>
      )}
    </div>
    <div className="mt-1 text-[14px] text-ink-muted">
      {[o.organization, o.location, detail.company?.industry].filter(Boolean).join(" · ")}
    </div>
  </div>
</div>
```
Stage stepper (a row of buttons; clicking calls `updateStage(o.id, stage, "moved from detail")` then reloads). Stages: read the pipeline order from the board if available, or hardcode `["new","qualifying","analyzing","active","in_dialogue","won","lost"]`. Active stage = `bg-accent text-white`, others = `bg-surface border border-line text-ink-muted`:
```tsx
<div className="my-5 flex flex-wrap gap-1.5">
  {STAGES.map((st) => (
    <button key={st} onClick={() => updateStage(o.id, st, "moved from detail").then(load)}
      className={`rounded-md px-3 py-1.5 text-[12.5px] font-semibold capitalize transition ${
        o.stage === st ? "bg-accent text-white" : "border border-line bg-surface text-ink-muted hover:bg-accent-tint hover:text-accent"
      }`}>{st.replace("_", " ")}</button>
  ))}
</div>
```
Two-column body (`flex flex-wrap gap-5 items-start`):
- **Left column** (`flex-1 min-w-[340px] flex flex-col gap-4.5`): a "Role overview" card (`o.summary`), a "Company" card (industry/size/HQ from `detail.company`, source from `o.source`), "Your notes" (if notes data — otherwise omit), the Briefing card (`detail.briefing`), Communications, and Contacts (with the add-contact form preserved).
- **Right column** (`w-[360px] flex-none flex flex-col gap-4.5`): a "What automation handled" card listing recent `detail.artifacts` + `detail.decisions` (each a row with a small green check chip + label + provenance/time); a "Quick actions" card with buttons (Advance stage → next stage via updateStage; and the existing per-row actions); the Applications card; and the Actions card (with `completeAction`).

Distribute ALL the existing sections across the two columns as cards — none dropped. Use `font-mono text-[10.5px] text-ink-subtle` for ids/urls/timestamps. Add `const STAGES = ["new","qualifying","analyzing","active","in_dialogue","won","lost"];` near the top.

Import `updateStage` from `@/lib/api` (add to the existing import).

- [ ] **Step 3: Build** — `npm --prefix frontend install` then `npm --prefix frontend run build` → succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/OpportunityDetailTab.tsx frontend/app/page.tsx
git commit -m "feat(ui): rebuild opportunity Detail to Job Hunter design (header, stage stepper, two-column cards)"
```
