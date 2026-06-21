# Companies Restyle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Restyle `CompaniesTab` to the Job Hunter design — a responsive grid of auto-enriched company cards — preserving the backfill action and linked-role navigation.

## Global Constraints
- PRESERVE: `fetchCompanies`/`fetchOpportunities` load, the backfill button (its handler + busy state), and the linked-roles `onOpen` navigation.
- Job Hunter tokens; literal Tailwind classes. Frontend build must pass.
- Do NOT invoke any finishing/branch skill — stop after committing.

---

### Task 1: Card-grid restyle

**Files:** Modify `frontend/app/components/CompaniesTab.tsx`.

- [ ] **Step 1: Rebuild the render** (keep all state/handlers)

READ `CompaniesTab.tsx`. Keep the data load, the backfill button handler + `busy`, the `linked` computation (roles per company), and `onOpen`. Replace the RENDER with:
- A header: title `Companies` (`text-[22px] font-bold tracking-tight text-ink`) + a subtitle line (`text-[13.5px] text-ink-muted`) reading `{companies.length} companies · {opps.length} roles tracked — profiles auto-enriched.`, and the backfill button on the right (`rounded-md bg-accent px-3.5 py-2 text-[13px] font-semibold text-white hover:bg-accent-ink disabled:opacity-50`).
- Empty state (`text-ink-subtle`) when no companies.
- A responsive grid: `grid gap-3.5 [grid-template-columns:repeat(auto-fill,minmax(330px,1fr))]`. Each company → a card `rounded-xl border border-line bg-surface p-4.5 transition hover:border-line-strong hover:shadow-pop`:
```tsx
<div key={c.id} className="rounded-xl border border-line bg-surface p-4 transition hover:border-line-strong hover:shadow-pop">
  <div className="flex items-start gap-3">
    <div className="flex h-10 w-10 flex-none items-center justify-center rounded-md bg-accent-tint text-[13px] font-bold text-accent">
      {c.name.slice(0, 2).toUpperCase()}
    </div>
    <div className="min-w-0 flex-1">
      <div className="truncate text-[14.5px] font-semibold text-ink">{c.name}</div>
      <div className="truncate text-[12.5px] text-ink-muted">
        {[c.industry, c.size, c.hq_location].filter(Boolean).join(" · ") || "—"}
      </div>
    </div>
    {c.ats_vendor && (
      <span className="flex-none rounded-xs bg-surface-sunk px-1.5 py-0.5 font-mono text-[10px] text-ink-subtle">{c.ats_vendor}</span>
    )}
  </div>
  {c.summary && <p className="mt-2.5 line-clamp-2 text-[12.5px] leading-snug text-ink-body">{c.summary}</p>}
  <div className="mt-3 border-t border-line-soft pt-2.5">
    <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-subtle">
      {linked.length} role{linked.length === 1 ? "" : "s"}
    </div>
    <div className="mt-1.5 flex flex-col gap-1">
      {linked.slice(0, 4).map((o) => (
        <button key={o.id} onClick={() => onOpen(o.id)} className="truncate text-left text-[12.5px] text-accent hover:underline">
          {o.title}
        </button>
      ))}
    </div>
  </div>
</div>
```
(`linked` = the opportunities whose organization matches the company — reuse the existing matching logic from the current file; if it currently matches by `c.name`, keep that.)
- Wrap the page in `<div className="min-h-0 flex-1 overflow-y-auto p-5">`. Use `FetchError` on load failure if the current file does.

- [ ] **Step 2: Build** — `npm --prefix frontend install` then `npm --prefix frontend run build` → succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/CompaniesTab.tsx
git commit -m "feat(ui): restyle Companies to the Job Hunter auto-enriched card grid"
```
