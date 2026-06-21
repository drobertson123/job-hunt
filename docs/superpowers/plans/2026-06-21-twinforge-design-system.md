# Adopt TwinForge Design Language — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-skin Opportunity Hunter to the TwinForge Design Language (tokens + primitives + AppShell), all features intact.

**Architecture:** TF tokens → Tailwind theme + Inter/JetBrains Mono; four primitive components; `page.tsx` restructured into AppShell (TopBar + 200px sectioned LeftNav replacing the horizontal nav + StatusBar); deep-teal accent throughout.

**Tech Stack:** Next.js (App Router, static export), React, Tailwind CSS.

## Global Constraints
- Tokens are the contract — use the EXACT hex/scale values below. Accent = teal `#0f766e` only for brand + primary/active affordances (NOT blue). Flat: borders over shadows. Tight radius (2–6px).
- All 12 nav destinations stay reachable: LeftNav item keys map 1:1 to the `canvasTab` union (workspace, profile, applications, briefing, detail, board, attention, companies, actions, interviews, sources, weekly). The render-branch chain in page.tsx is preserved.
- Tailwind JIT only sees LITERAL class strings — never build class names by string concatenation; use literal lookup maps.
- Frontend worktree has no node_modules: `npm --prefix frontend install` first; `npm --prefix frontend run build` must succeed.
- Do NOT invoke any finishing/branch skill — stop after committing and reporting.

---

### Task 1: Design tokens, fonts, and primitive components

**Files:**
- Modify: `frontend/tailwind.config.ts`
- Modify: `frontend/app/globals.css`
- Create: `frontend/app/components/ui/Pill.tsx`, `Button.tsx`, `Panel.tsx`, `IconBtn.tsx`

- [ ] **Step 1: Extend the Tailwind theme**

Replace `frontend/tailwind.config.ts` with:
```ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#f5f6f7",
        surface: { DEFAULT: "#ffffff", alt: "#fafbfc", sunk: "#edeef0" },
        line: { DEFAULT: "#d8dbe0", soft: "#e8eaee", strong: "#b5bac2" },
        ink: { DEFAULT: "#0f1620", muted: "#5a6270", subtle: "#8a929e" },
        accent: { DEFAULT: "#0f766e", soft: "#e6f2f0", ink: "#0a4f49" },
        ok: { DEFAULT: "#2f7d4e", soft: "#e5f3ea" },
        override: { DEFAULT: "#3b7bb8", soft: "#e6eef7" },
        warn: { DEFAULT: "#b45816", soft: "#fbecdd" },
        error: { DEFAULT: "#a6342a", soft: "#f5e1df" },
        stale: { DEFAULT: "#7a8494", soft: "#e5e7ea" },
      },
      fontFamily: {
        sans: ['Inter', '"Segoe UI"', "-apple-system", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', '"SF Mono"', "Menlo", "Consolas", "monospace"],
      },
      borderRadius: { xs: "2px", sm: "3px", md: "4px", lg: "6px" },
      boxShadow: {
        panel: "0 1px 0 rgba(15,22,32,0.04)",
        pop: "0 1px 2px rgba(15,22,32,0.06), 0 4px 12px rgba(15,22,32,0.08)",
        modal: "0 8px 32px rgba(15,22,32,0.18)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
```

- [ ] **Step 2: Fonts + base in globals.css**

Replace `frontend/app/globals.css` with:
```css
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap");
@tailwind base;
@tailwind components;
@tailwind utilities;

html,
body,
#__next {
  height: 100%;
}

body {
  @apply bg-bg font-sans text-ink antialiased;
  font-size: 12.5px;
}
```

- [ ] **Step 3: Create the primitives**

`frontend/app/components/ui/Pill.tsx`:
```tsx
import type { ReactNode } from "react";

type Tone = "neutral" | "accent" | "ok" | "override" | "warn" | "error" | "stale";

const TONE: Record<Tone, string> = {
  neutral: "bg-surface-sunk text-ink-muted",
  accent: "bg-accent-soft text-accent-ink",
  ok: "bg-ok-soft text-ok",
  override: "bg-override-soft text-override",
  warn: "bg-warn-soft text-warn",
  error: "bg-error-soft text-error",
  stale: "bg-stale-soft text-stale",
};
const SOLID: Record<Tone, string> = {
  neutral: "bg-ink-muted text-white",
  accent: "bg-accent text-white",
  ok: "bg-ok text-white",
  override: "bg-override text-white",
  warn: "bg-warn text-white",
  error: "bg-error text-white",
  stale: "bg-stale text-white",
};

export default function Pill({
  tone = "neutral",
  size = "md",
  mono = false,
  solid = false,
  children,
}: {
  tone?: Tone;
  size?: "sm" | "md";
  mono?: boolean;
  solid?: boolean;
  children: ReactNode;
}) {
  const pad = size === "sm" ? "px-1.5 py-px text-[10px]" : "px-2 py-0.5 text-[11px]";
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-sm font-semibold leading-tight ${
        mono ? "font-mono" : ""
      } ${pad} ${solid ? SOLID[tone] : TONE[tone]}`}
    >
      {children}
    </span>
  );
}
```

`frontend/app/components/ui/Button.tsx`:
```tsx
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Kind = "primary" | "ghost" | "outline" | "danger";

const KIND: Record<Kind, string> = {
  primary: "border border-accent bg-accent text-white hover:bg-accent-ink",
  ghost: "border border-transparent bg-transparent text-ink hover:bg-surface-sunk",
  outline: "border border-line bg-surface text-ink hover:bg-surface-alt",
  danger: "border border-line bg-surface text-error hover:bg-error-soft",
};

export default function Button({
  kind = "ghost",
  size = "md",
  icon,
  children,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  kind?: Kind;
  size?: "sm" | "md";
  icon?: ReactNode;
}) {
  const pad = size === "sm" ? "px-2 py-1 text-[11.5px]" : "px-3 py-1.5 text-[12.5px]";
  return (
    <button
      {...rest}
      className={`inline-flex items-center gap-1.5 rounded-sm font-medium transition disabled:opacity-50 ${pad} ${KIND[kind]} ${className}`}
    >
      {icon}
      {children}
    </button>
  );
}
```

`frontend/app/components/ui/Panel.tsx`:
```tsx
import type { ReactNode } from "react";

export default function Panel({
  title,
  actions,
  children,
  className = "",
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex min-h-0 flex-col rounded-sm border border-line bg-surface ${className}`}>
      {title && (
        <div className="flex items-center justify-between rounded-t-sm border-b border-line-soft bg-surface-alt px-3 py-2">
          <span className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-muted">
            {title}
          </span>
          {actions && <div className="flex gap-1">{actions}</div>}
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
    </div>
  );
}
```

`frontend/app/components/ui/IconBtn.tsx`:
```tsx
import type { ButtonHTMLAttributes, ReactNode } from "react";

export default function IconBtn({
  active,
  children,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean; children: ReactNode }) {
  return (
    <button
      {...rest}
      className={`inline-flex h-[26px] w-[26px] items-center justify-center rounded-sm border text-ink ${
        active ? "border-line-soft bg-surface-sunk" : "border-transparent"
      } ${className}`}
    >
      {children}
    </button>
  );
}
```

- [ ] **Step 4: Build**

Run: `npm --prefix frontend install` then `npm --prefix frontend run build` — must succeed (the new token classes used by primitives compile; tree-shaking is fine).

- [ ] **Step 5: Commit**

```bash
git add frontend/tailwind.config.ts frontend/app/globals.css frontend/app/components/ui/
git commit -m "feat(ui): TwinForge design tokens (teal accent, Inter/JetBrains Mono, tight radius) + Pill/Button/Panel/IconBtn primitives"
```

---

### Task 2: AppShell — TopBar + LeftNav sidebar + StatusBar

**Files:**
- Create: `frontend/app/components/LeftNav.tsx`
- Modify: `frontend/app/page.tsx`
- Delete (stop using): the `CanvasNav` element in page.tsx (component file may remain unused)

- [ ] **Step 1: Create `LeftNav.tsx`** (replaces the horizontal CanvasNav)

```tsx
"use client";

import Pill from "./ui/Pill";

type Tone = "neutral" | "warn";
type Item = { key: string; label: string; tone?: Tone };

const SECTIONS: { title: string; items: Item[] }[] = [
  {
    title: "Pipeline",
    items: [
      { key: "board", label: "Board" },
      { key: "detail", label: "Detail" },
      { key: "attention", label: "Attention", tone: "warn" },
      { key: "weekly", label: "This week" },
    ],
  },
  {
    title: "Track",
    items: [
      { key: "applications", label: "Applications" },
      { key: "interviews", label: "Interviews" },
      { key: "actions", label: "Actions" },
    ],
  },
  {
    title: "Research",
    items: [
      { key: "companies", label: "Companies" },
      { key: "sources", label: "Sources" },
      { key: "briefing", label: "Briefing" },
    ],
  },
  {
    title: "You",
    items: [
      { key: "workspace", label: "Workspace" },
      { key: "profile", label: "Profile" },
    ],
  },
];

export default function LeftNav({
  active,
  onSelect,
  counts,
}: {
  active: string;
  onSelect: (k: string) => void;
  counts: Record<string, number>;
}) {
  return (
    <nav className="flex w-[196px] flex-shrink-0 flex-col gap-3.5 overflow-y-auto border-r border-line bg-surface py-3">
      {SECTIONS.map((sec) => (
        <div key={sec.title}>
          <div className="px-4 pb-1 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-subtle">
            {sec.title}
          </div>
          {sec.items.map((it) => {
            const on = active === it.key;
            const c = counts[it.key];
            return (
              <button
                key={it.key}
                onClick={() => onSelect(it.key)}
                className={`flex w-full items-center justify-between border-l-2 px-4 py-1.5 text-left text-[12.5px] transition ${
                  on
                    ? "border-accent bg-accent-soft font-semibold text-ink"
                    : "border-transparent font-medium text-ink-muted hover:bg-surface-sunk"
                }`}
              >
                <span>{it.label}</span>
                {typeof c === "number" && c > 0 && (
                  <Pill tone={on ? "accent" : it.tone ?? "neutral"} size="sm">
                    {c}
                  </Pill>
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

- [ ] **Step 2: Restructure `page.tsx` into the AppShell**

Read `frontend/app/page.tsx`. Make these changes (preserve ALL logic, state, the render-branch chain, and SettingsBadge):

(a) Add imports: `import LeftNav from "./components/LeftNav";` (keep/remove the `CanvasNav` import — it will be unused; remove it to avoid lint noise).

(b) Replace the existing `<header …>` block (the branded indigo header from the prior refresh) with the TwinForge TopBar:
```tsx
<header className="flex h-11 flex-shrink-0 items-center justify-between border-b border-line bg-surface px-3">
  <div className="flex items-center gap-2">
    <span className="relative h-5 w-5 rounded-sm bg-accent">
      <span className="absolute inset-1 rounded-[1px] border-[1.6px] border-white" />
    </span>
    <span className="text-[13.5px] font-semibold tracking-tight text-ink">
      Opportunity Hunter
    </span>
  </div>
  <SettingsBadge settings={settings} onSaved={setSettings} />
</header>
```

(c) Wrap the body so LeftNav sits left of the chat+canvas. The current body is:
```tsx
<div className="flex min-h-0 flex-1 flex-col md:flex-row"> … chat <section> … canvas <section> … </div>
```
Change it to put LeftNav first, then the chat+canvas row:
```tsx
<div className="flex min-h-0 flex-1">
  <LeftNav
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
  <div className="flex min-h-0 flex-1 flex-col md:flex-row">
    {/* existing chat <section> … and canvas <section> … unchanged EXCEPT step (d) */}
  </div>
</div>
```

(d) In the canvas `<section>`, DELETE the `<CanvasNav … />` element (the top nav strip) — navigation now lives in LeftNav. Keep everything else in that section (the `{canvasTab === … ? … }` render-branch chain) exactly as-is.

(e) Add a StatusBar as the last child of `<main>` (after the body div):
```tsx
<footer className="flex h-6 flex-shrink-0 items-center gap-3 border-t border-line bg-surface-alt px-3 font-mono text-[11px] text-ink-muted">
  <span>{opps.length} opportunities</span>
  <span>·</span>
  <span>{applications.length} applications</span>
  <span>·</span>
  <span>{openActionCount} open actions</span>
  <span>·</span>
  <span>{attentionCount} need attention</span>
  <span className="flex-1" />
  <span>opportunity-hunter</span>
</footer>
```

(f) Ensure `<main>` is `className="flex h-screen flex-col bg-bg text-ink"`.

- [ ] **Step 3: Retheme the chat pane + capability bar to tokens**

Within the chat `<section>` in page.tsx:
- Capability bar container: change `bg-slate-50` → `bg-surface-alt`, border to `border-line`.
- Capability buttons: change `className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700 transition hover:bg-indigo-50 hover:text-indigo-700 disabled:opacity-40"` → `className="rounded-sm border border-line bg-surface px-2.5 py-1 text-[11.5px] font-medium text-ink transition hover:bg-surface-sunk disabled:opacity-40"`.
- The opportunity `<select>`: `border` → `border-line`, `rounded` → `rounded-sm`.
- Chat input: `className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"` → `className="flex-1 rounded-sm border border-line px-3 py-2 text-[12.5px] focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"`.
- Send button: `className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-50"` → `className="rounded-sm bg-accent px-4 py-2 text-[12.5px] font-medium text-white transition hover:bg-accent-ink disabled:opacity-50"`.
- The chat thread border classes `border-r`/`border-t`/`border-b` → `border-line` variants (e.g. `border-r border-line`).

- [ ] **Step 4: Build**

Run: `npm --prefix frontend run build` — must succeed. Confirm all 12 nav keys still render their branches (no `canvasTab` value lost).

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components/LeftNav.tsx frontend/app/page.tsx
git commit -m "feat(ui): TwinForge AppShell — 44px TopBar, sectioned LeftNav sidebar, mono StatusBar; retheme chat pane to tokens"
```

---

### Task 3: Accent-consistency pass across tab components

**Files:**
- Modify: tab components under `frontend/app/components/` that use `bg-slate-900` primary buttons or leftover `indigo-*`/`rounded-full` from the prior refresh.

- [ ] **Step 1: Find the accent-bearing affordances**

Run (from worktree root):
```bash
grep -rln "bg-slate-900\|indigo-\|rounded-full" frontend/app --include=*.tsx
```
This lists components with primary buttons / old-accent classes (e.g. ActionsTab, WeeklyTab, SourcesTab, InterviewsTab, ProfileTab, and the now-unused CanvasNav).

- [ ] **Step 2: Swap to the teal accent (literal replacements)**

In each listed file EXCEPT `CanvasNav.tsx` (leave it — it is no longer rendered), replace:
- `bg-slate-900` (primary buttons) → `bg-accent` ; and adjacent `hover:` if present → `hover:bg-accent-ink`. (Keep `text-white`.)
- any `bg-indigo-600`/`bg-indigo-500` → `bg-accent`/`bg-accent-ink`; `text-indigo-700` → `text-accent-ink`; `hover:bg-indigo-50` → `hover:bg-accent-soft`; `ring-indigo-500`/`border-indigo-500` → `ring-accent`/`border-accent`.
- Leave neutral slate (slate-100/200/400/500/600/700 text/bg/border) untouched — these read fine as TF grays.

Do NOT change logic, only className color tokens. Verify each edit against the actual file (read first).

- [ ] **Step 3: Mono for identifiers (light touch, optional-but-included)**

In `OpportunityDetailTab.tsx` (and any place showing a raw opportunity `id`, `url`, or `dedupe_key`), wrap that value in `font-mono text-[11px]` if not already monospaced. Skip if it complicates the JSX — this is a nicety, not required for the build.

- [ ] **Step 4: Build**

Run: `npm --prefix frontend run build` — must succeed.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components
git commit -m "feat(ui): unify primary/active affordances to the teal accent across tabs"
```
