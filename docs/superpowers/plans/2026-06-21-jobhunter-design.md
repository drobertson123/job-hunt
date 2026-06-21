# "Job Hunter" Design Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Re-skin the app to the user's "Job Hunter" design — warm-cream + indigo/purple, Figtree/JetBrains Mono, a 76px icon nav rail, a greeting top bar, and a restyled Board.

**Architecture:** Re-point the existing Tailwind semantic tokens (bg/surface/line/ink/accent/ok/warn/error) to the Job Hunter palette so the whole app re-themes at once; then bespoke shell (IconRail + TopBar replacing LeftNav + header) and a Board restyle.

## Global Constraints
- Translate the design (don't transcribe the mockup HTML). Write components in the app's React/Tailwind idiom.
- Keep ALL 13 canvas destinations reachable (the IconRail keys map 1:1 to the `canvasTab` union: workspace, profile, applications, briefing, detail, board, attention, companies, actions, interviews, sources, weekly, library).
- Tailwind JIT sees only literal class strings.
- Frontend worktree has no node_modules: `npm --prefix frontend install` first; `npm --prefix frontend run build` must succeed.
- Do NOT invoke any finishing/branch skill — stop after committing and reporting.

---

### Task 1: Token palette + fonts (re-theme everything)

**Files:** Modify `frontend/tailwind.config.ts`, `frontend/app/globals.css`.

- [ ] **Step 1: Re-point the Tailwind theme**

Replace the `theme.extend` block in `frontend/tailwind.config.ts` with the Job Hunter palette (keep existing token NAMES so all components re-theme; add the new ones):
```ts
    extend: {
      colors: {
        bg: "#f6f4f0",
        paper: "#efeae2",                              // kanban columns
        surface: { DEFAULT: "#ffffff", alt: "#fbfaf8", sunk: "#f1ede7" },
        line: { DEFAULT: "#ebe7e1", soft: "#f1ede7", strong: "#e6e0d6" },
        ink: { DEFAULT: "#211e2b", body: "#3b3746", muted: "#6c6678", subtle: "#9a95a3", faint: "#a39c92" },
        panel: "#211e2b",                              // dark cards
        accent: { DEFAULT: "#5750d9", ink: "#4840c0", mid: "#7a73e6", light: "#a8a3f0", soft: "#c9c5f2", tint: "#ecebfb" },
        ok: { DEFAULT: "#3f9a6e", deep: "#2f7a57", soft: "#e8f3ec", mint: "#7ee0b0" },
        warn: { DEFAULT: "#c98a2e", soft: "#f7efe1" },
        error: { DEFAULT: "#d35a4a", soft: "#fbecea" },
      },
      fontFamily: {
        sans: ['Figtree', '"Segoe UI"', "-apple-system", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', '"SF Mono"', "Menlo", "Consolas", "monospace"],
      },
      borderRadius: { xs: "4px", sm: "7px", md: "11px", lg: "14px", xl: "16px" },
      boxShadow: {
        panel: "0 1px 0 rgba(33,30,43,0.04)",
        card: "0 8px 22px rgba(33,30,43,0.10)",
        accent: "0 3px 10px rgba(87,80,217,0.25)",
        pop: "0 6px 16px rgba(33,30,43,0.08)",
        modal: "0 12px 32px rgba(33,30,43,0.18)",
      },
    },
```
(Note: the radius tokens xs/sm/md/lg are bumped to the design's softer scale; `rounded-sm` etc. across the app become gently rounder — intended.)

- [ ] **Step 2: Fonts + base in globals.css**

Replace the Google-Fonts `@import` line in `frontend/app/globals.css` with:
```css
@import url("https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap");
```
Keep the `@tailwind` directives and the `body { @apply bg-bg font-sans text-ink antialiased; }` base (it now resolves to the warm palette + Figtree). Add a warm scrollbar rule:
```css
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: #e0dbd3; border-radius: 6px; border: 3px solid #f6f4f0; }
::-webkit-scrollbar-thumb:hover { background: #cfc9bf; }
```

- [ ] **Step 3: Build** — `npm --prefix frontend install` then `npm --prefix frontend run build` → succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/tailwind.config.ts frontend/app/globals.css
git commit -m "feat(ui): adopt Job Hunter palette + Figtree/JetBrains Mono (re-points tokens app-wide)"
```

---

### Task 2: Icon nav rail + greeting top bar

**Files:** Create `frontend/app/components/IconRail.tsx`; Modify `frontend/app/page.tsx`.

- [ ] **Step 1: Create `IconRail.tsx`** (replaces LeftNav)

A 76px white rail. Driven by a config array (each item: `key` matching a `canvasTab`, `label` for the tooltip, and an inline `<svg>` icon). At top: a 42px accent rounded logo. The icon column scrolls. Active item = `bg-accent-tint text-accent`; inactive = `text-ink-muted hover:bg-surface-sunk`, each a 44px rounded-md button with `title={label}`. At the bottom (mt-auto): a pulsing green dot (`bg-ok`) titled "Automation active" and a 38px dark circular avatar showing the user's initials.
```tsx
"use client";

import type { ReactNode } from "react";

type Item = { key: string; label: string; icon: ReactNode };

const I = (d: string, sw = 1.7) => (
  <svg width="20" height="20" viewBox="0 0 21 21" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round">{<path d={d} />}</svg>
);

const ITEMS: Item[] = [
  { key: "board", label: "Board", icon: (<svg width="20" height="20" viewBox="0 0 21 21" fill="none" stroke="currentColor" strokeWidth={1.7}><rect x="2.5" y="3" width="4.2" height="15" rx="1.4"/><rect x="8.4" y="3" width="4.2" height="10" rx="1.4"/><rect x="14.3" y="3" width="4.2" height="13" rx="1.4"/></svg>) },
  { key: "weekly", label: "This week", icon: I("M3 6h7M14 6h4M3 15h4M11 15h7") },
  { key: "attention", label: "Attention", icon: I("M10.5 2.5L2 17h17z M10.5 8v4 M10.5 14.5v.1") },
  { key: "applications", label: "Applications", icon: I("M5 3h6l5 5v10H5z M11 3v5h5 M8 11h5M8 14h5") },
  { key: "interviews", label: "Interviews", icon: I("M4 4h13v13H4z M4 8h13 M8 2v3 M13 2v3") },
  { key: "companies", label: "Companies", icon: I("M3 3.5h9v14H3z M12 8h5.5v9.5H12 M5.5 7h1M9 7h1M5.5 10h1M9 10h1") },
  { key: "sources", label: "Sources", icon: I("M10.5 16a5.5 5.5 0 100-11 5.5 5.5 0 000 11z M10.5 10.5v.1 M10.5 4v1.5M10.5 15.5V17M4 10.5H2.5M18.5 10.5H17") },
  { key: "library", label: "Library", icon: I("M5 3h11v15H5z M5 3a1.5 1.5 0 000 3h11 M9 7h4") },
  { key: "interviews-cal", label: "Documents", icon: I("M5 3h6l5 5v10H5z M11 3v5h5") },
  { key: "profile", label: "Profile", icon: I("M10.5 10.5a3.2 3.2 0 100-6.4 3.2 3.2 0 000 6.4z M4 18c0-3.4 2.9-5.5 6.5-5.5S17 14.6 17 18") },
  { key: "workspace", label: "Workspace", icon: I("M3 5.5h5l1.5 2H18v9.5H3z") },
];

export default function IconRail({
  active,
  onSelect,
  initials = "DR",
}: {
  active: string;
  onSelect: (k: string) => void;
  initials?: string;
}) {
  // de-dupe: the "Documents" alias points at workspace
  const items = ITEMS.map((it) => (it.key === "interviews-cal" ? { ...it, key: "workspace" } : it)).filter(
    (it, i, a) => a.findIndex((x) => x.key === it.key) === i
  );
  return (
    <nav className="flex w-[76px] flex-none flex-col items-center gap-2.5 border-r border-line bg-surface py-4">
      <div className="mb-3 flex h-[42px] w-[42px] items-center justify-center rounded-md bg-accent shadow-accent">
        <svg width="22" height="22" viewBox="0 0 22 22" fill="none"><circle cx="6" cy="6" r="2.6" fill="#fff"/><circle cx="16" cy="11" r="2.6" fill="#fff"/><circle cx="7" cy="16" r="2.6" fill="#fff"/><path d="M6 6 L16 11 M16 11 L7 16" stroke="#fff" strokeWidth="1.4" strokeLinecap="round" opacity=".75"/></svg>
      </div>
      <div className="flex w-full flex-1 flex-col items-center gap-1.5 overflow-y-auto py-0.5">
        {items.map((it) => {
          const on = active === it.key;
          return (
            <button
              key={it.key}
              title={it.label}
              onClick={() => onSelect(it.key)}
              className={`flex h-11 w-11 flex-none items-center justify-center rounded-md transition ${
                on ? "bg-accent-tint text-accent" : "text-ink-muted hover:bg-surface-sunk"
              }`}
            >
              {it.icon}
            </button>
          );
        })}
      </div>
      <div className="mt-auto flex flex-col items-center gap-3">
        <span className="h-2 w-2 animate-pulse rounded-full bg-ok" title="Automation active" />
        <span className="flex h-[38px] w-[38px] items-center justify-center rounded-full bg-panel text-[13px] font-semibold text-white">
          {initials}
        </span>
      </div>
    </nav>
  );
}
```

- [ ] **Step 2: Restructure `page.tsx`** (read it first; preserve all logic + the render-branch chain)

(a) Add `import IconRail from "./components/IconRail";` and remove the `LeftNav` import/usage.
(b) Replace the existing `<header …>` (the TwinForge top bar) with the greeting top bar:
```tsx
<header className="flex h-[68px] flex-none items-center justify-between gap-5 border-b border-line bg-bg px-7">
  <div className="min-w-0">
    <div className="text-[21px] font-bold tracking-tight text-ink">Good morning</div>
    <div className="mt-0.5 text-[13px] text-ink-muted">
      Your hunt ·{" "}
      <span className="font-semibold text-error">{attentionCount} decisions</span> need you today
    </div>
  </div>
  <div className="flex flex-none items-center gap-3">
    <SettingsBadge settings={settings} onSaved={setSettings} />
    <button
      onClick={() => setCanvasTab("board")}
      className="flex items-center gap-1.5 rounded-md bg-accent px-4 py-2.5 text-[13.5px] font-semibold text-white shadow-accent transition hover:bg-accent-ink"
    >
      <svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round"><path d="M7.5 3v9M3 7.5h9"/></svg>
      Add job
    </button>
  </div>
</header>
```
(c) Replace `<LeftNav … />` in the body with:
```tsx
<IconRail active={canvasTab} onSelect={(t) => setCanvasTab(t as typeof canvasTab)} />
```
(d) Remove the StatusBar `<footer>` (its counts now live in the top bar).
(e) Ensure `<main>` stays `className="flex h-screen flex-col bg-bg text-ink"`. Leave the chat pane + canvas render-branch chain intact; they inherit the new tokens.

- [ ] **Step 3: Build** — `npm --prefix frontend run build` → succeeds; confirm all 13 `canvasTab` values still render.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/IconRail.tsx frontend/app/page.tsx
git commit -m "feat(ui): Job Hunter shell — 76px icon rail + greeting top bar"
```

---

### Task 3: Board restyle (hero)

**Files:** Modify `frontend/app/components/BoardTab.tsx`.

- [ ] **Step 1: Restyle the kanban to the Job Hunter look**

Read `BoardTab.tsx`. Keep all dnd-kit logic, the `fetchPipeline`/`updateStage` calls, the filter state, and the stage columns — change ONLY the presentation:
- Column wrapper: `w-[290px] flex-none flex flex-col rounded-xl border border-line-strong bg-paper p-2.5` with a header row (stage label, count pill) in `text-ink font-bold text-[13.5px]`.
- `Card`: white `rounded-lg border border-line bg-surface p-3.5` with `hover:shadow-card hover:-translate-y-px transition`; a left accent stripe (`absolute left-0 top-0 h-full w-[3px] rounded-l-lg bg-accent`); an initials chip (`h-8 w-8 rounded-md bg-accent-tint text-accent text-[11px] font-bold` from the org's first letters); the company name (`text-[13px] font-semibold`) + (if present) a mono source line (`font-mono text-[10px] text-ink-subtle`); a match/fit pill on the right (`text-accent bg-accent-tint rounded-xs px-1.5 py-0.5 text-[11px] font-semibold` showing `Fit {opp.fit_score}` when set); the role/title (`text-[13.5px] font-semibold mt-2`); and meta (`text-[12px] text-ink-muted`).
- An "Add job" dashed button at the column bottom (`border-1.5 border-dashed border-line-strong rounded-lg text-ink-faint`).
Keep it data-driven from the existing `OpportunityFull` fields (title, organization, fit_score, stage); do not invent fields that don't exist — derive initials from `organization || title`.

- [ ] **Step 2: Auto-discovery strip (top of board)**

Above the columns, add a strip: `flex items-center gap-3.5 rounded-md border border-line bg-surface px-4 py-2.5` with a pulsing accent dot, "Auto-discovery" label, a thin progress bar (`h-[5px] bg-accent-tint` with an inner `bg-accent` bar at ~60% width), and a mono status (`font-mono text-[11.5px] text-ink-muted`) — static/illustrative is fine (this mirrors the daily-search scheduler).

- [ ] **Step 3: Build + Commit** — `npm --prefix frontend run build` → succeeds.

```bash
git add frontend/app/components/BoardTab.tsx
git commit -m "feat(ui): Job Hunter board — kanban cards, accent stripe, discovery strip"
```
