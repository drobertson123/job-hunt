# GUI Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A cleaner, more usable GUI with all the same features — grouped pill navigation + an indigo accent theme + branded header, shell-scoped so tabs inherit it.

**Architecture:** A new data-driven `CanvasNav` component replaces 12 inline tab buttons; `page.tsx` header/chat get accent styling. No backend, no feature changes.

**Tech Stack:** Next.js (App Router, static export), React, Tailwind CSS.

## Global Constraints
- All 12 existing tabs MUST remain reachable: `CanvasNav` item keys map 1:1 to the `canvasTab` union members (`workspace, profile, applications, briefing, detail, board, attention, companies, actions, interviews, sources, weekly`). Do not rename or drop any.
- The render-branch chain BELOW the nav (`{canvasTab === "workspace" ? (...) : ...}`) is NOT touched — only the nav button block is replaced.
- Accent = indigo-600 for primary/active; secondary controls stay slate. No new dependencies.
- Frontend has no node_modules in the worktree: run `npm --prefix frontend install` first, then `npm --prefix frontend run build` must succeed.
- Do NOT invoke any finishing/branch skill — stop after committing and reporting.

---

### Task 1: `CanvasNav` component + swap it into page.tsx

**Files:**
- Create: `frontend/app/components/CanvasNav.tsx`
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Create `CanvasNav.tsx`**

```tsx
"use client";

type Item = { key: string; label: string; count?: number };

export default function CanvasNav({
  active,
  onSelect,
  counts,
}: {
  active: string;
  onSelect: (t: string) => void;
  counts: Record<string, number>;
}) {
  const groups: Item[][] = [
    [
      { key: "board", label: "Board", count: counts.board },
      { key: "detail", label: "Detail" },
      { key: "attention", label: "Attention", count: counts.attention },
      { key: "weekly", label: "This week" },
    ],
    [
      { key: "applications", label: "Applications", count: counts.applications },
      { key: "interviews", label: "Interviews" },
      { key: "actions", label: "Actions", count: counts.actions },
    ],
    [
      { key: "companies", label: "Companies", count: counts.companies },
      { key: "sources", label: "Sources" },
      { key: "briefing", label: "Briefing" },
    ],
    [
      { key: "workspace", label: "Workspace", count: counts.workspace },
      { key: "profile", label: "Profile" },
    ],
  ];

  return (
    <nav className="flex flex-wrap items-center gap-1 border-b border-slate-200 bg-white px-3 py-2">
      {groups.map((items, gi) => (
        <div key={gi} className="flex flex-wrap items-center gap-1">
          {gi > 0 && (
            <span className="mx-1 hidden h-4 w-px bg-slate-200 sm:inline-block" aria-hidden />
          )}
          {items.map((it) => {
            const on = active === it.key;
            return (
              <button
                key={it.key}
                onClick={() => onSelect(it.key)}
                className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition ${
                  on
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {it.label}
                {typeof it.count === "number" && it.count > 0 && (
                  <span
                    className={`rounded-full px-1.5 text-[10px] ${
                      on ? "bg-white/25 text-white" : "bg-slate-200 text-slate-600"
                    }`}
                  >
                    {it.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
```

- [ ] **Step 2: Swap the nav block in `page.tsx`**

Read `frontend/app/page.tsx`. Add the import alongside the other component imports:
```tsx
import CanvasNav from "./components/CanvasNav";
```
Find the canvas-pane nav block — it opens with:
```tsx
<div className="flex gap-4 border-b px-4 text-sm font-medium">
```
and contains all twelve `<button …>` tab buttons, closing with its matching `</div>` just before the content render-branch chain (the first `{canvasTab === "workspace" ? (` … or similar). Replace that ENTIRE `<div>…</div>` block with:
```tsx
<CanvasNav
  active={canvasTab}
  onSelect={(t) => setCanvasTab(t as typeof canvasTab)}
  counts={{
    board: opps.length,
    attention: attentionCount,
    applications: applications.length,
    actions: openActionCount,
    companies: companyCount,
    workspace: artifacts.length + notes.length,
  }}
/>
```
Do NOT modify anything below this block (the `{canvasTab === … ? <Tab/> : …}` chain stays exactly as-is). Verify every union member still has a matching CanvasNav key (workspace, profile, applications, briefing, detail, board, attention, companies, actions, interviews, sources, weekly — all 12 present in the groups).

- [ ] **Step 3: Build**

Run: `npm --prefix frontend install` then `npm --prefix frontend run build`
Expected: build succeeds; no type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/CanvasNav.tsx frontend/app/page.tsx
git commit -m "feat(ui): grouped data-driven canvas navigation (pills, accent active)"
```

---

### Task 2: Accent theme — header, chat input/Send, capability bar

**Files:**
- Modify: `frontend/app/page.tsx` (header, chat input, Send button, capability buttons)

- [ ] **Step 1: Branded header**

In `page.tsx`, replace the header block:
```tsx
<header className="flex items-center justify-between border-b bg-white px-4 py-3">
  <h1 className="text-lg font-semibold">Opportunity Hunter</h1>
  <SettingsBadge settings={settings} onSaved={setSettings} />
</header>
```
with:
```tsx
<header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2.5">
  <div className="flex items-center gap-2.5">
    <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white">
      O
    </span>
    <div className="leading-tight">
      <h1 className="text-base font-semibold text-slate-900">Opportunity Hunter</h1>
      <p className="text-[11px] text-slate-400">Your job-hunt command center</p>
    </div>
  </div>
  <SettingsBadge settings={settings} onSaved={setSettings} />
</header>
```

- [ ] **Step 2: Chat input + Send accent**

In the chat input block, change the input className from:
```tsx
className="flex-1 rounded border px-3 py-2 text-sm"
```
to:
```tsx
className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
```
and the Send button className from:
```tsx
className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
```
to:
```tsx
className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-50"
```

- [ ] **Step 3: Capability button polish**

In the capability bar, change the capability button className from:
```tsx
className="rounded bg-slate-200 px-2 py-1 text-xs font-medium text-slate-800 hover:bg-slate-300 disabled:opacity-40"
```
to:
```tsx
className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700 transition hover:bg-indigo-50 hover:text-indigo-700 disabled:opacity-40"
```
Leave the opportunity `<select>` as-is.

- [ ] **Step 4: Build**

Run: `npm --prefix frontend run build`
Expected: build succeeds; no type errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(ui): indigo accent theme — branded header, chat input/Send, capability bar"
```
