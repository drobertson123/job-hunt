# Markdown Raw/Rendered Views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render Markdown-bearing boxes (artifact bodies, notes, profile summary) as formatted Markdown with a per-box Rendered/Raw toggle.

**Architecture:** One shared presentational React component `MarkdownView` (react-markdown + remark-gfm + Tailwind Typography `prose`), swapped in at three call sites that currently use `whitespace-pre-wrap`.

**Tech Stack:** Next.js (App Router, static export), React, Tailwind CSS, react-markdown, remark-gfm, @tailwindcss/typography.

## Global Constraints
- Default view is **Rendered**; Raw shows the exact stored Markdown source.
- No new backend behavior; no API changes. Frontend only.
- Verification is `npm --prefix frontend run build` (static export, type-checks) succeeding.
- Do NOT invoke any finishing/branch skill — implementers stop after committing and reporting.

---

### Task 1: Add deps, Tailwind Typography, and the `MarkdownView` component

**Files:**
- Modify: `frontend/package.json` (add deps)
- Modify: `frontend/tailwind.config.ts` (register typography plugin)
- Create: `frontend/app/components/MarkdownView.tsx`

**Interfaces:**
- Produces: `export default function MarkdownView({ text, className }: { text: string; className?: string })`

- [ ] **Step 1: Install dependencies**

Run (from worktree root):
```bash
npm --prefix frontend install react-markdown remark-gfm
npm --prefix frontend install -D @tailwindcss/typography
```
Expected: packages added to `frontend/package.json`, no peer-dep errors.

- [ ] **Step 2: Register the typography plugin**

Edit `frontend/tailwind.config.ts` so `plugins` is:
```ts
plugins: [require("@tailwindcss/typography")],
```
(Keep the rest of the config unchanged.)

- [ ] **Step 3: Create `MarkdownView.tsx`**

```tsx
"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function MarkdownView({
  text,
  className = "",
}: {
  text: string;
  className?: string;
}) {
  const [mode, setMode] = useState<"rendered" | "raw">("rendered");
  if (!text || !text.trim()) return null;

  return (
    <div className={className}>
      <div className="mb-1 flex justify-end gap-1 text-xs">
        {(["rendered", "raw"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={`rounded px-2 py-0.5 capitalize ${
              mode === m
                ? "bg-slate-700 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {m}
          </button>
        ))}
      </div>
      {mode === "rendered" ? (
        <div className="prose prose-sm max-w-none text-slate-700">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        </div>
      ) : (
        <pre className="whitespace-pre-wrap break-words font-mono text-sm text-slate-700">
          {text}
        </pre>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Verify the build compiles**

Run: `npm --prefix frontend run build`
Expected: build succeeds (component type-checks; unused-but-valid is fine).

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tailwind.config.ts frontend/app/components/MarkdownView.tsx
git commit -m "feat(ui): add MarkdownView with rendered/raw toggle"
```

---

### Task 2: Wire `MarkdownView` into the three Markdown sites

**Files:**
- Modify: `frontend/app/components/ArtifactCard.tsx` (expanded body block)
- Modify: `frontend/app/page.tsx` (workspace notes)
- Modify: `frontend/app/components/ProfileTab.tsx` (synthesized summary)

**Interfaces:**
- Consumes: `MarkdownView` from `./MarkdownView` (ArtifactCard, ProfileTab) / `./components/MarkdownView` (page.tsx — match the file's existing import style).

- [ ] **Step 1: ArtifactCard — render the expanded body**

In `frontend/app/components/ArtifactCard.tsx`, add the import (alongside other component imports):
```tsx
import MarkdownView from "./MarkdownView";
```
Replace the expanded-body block (currently a `div` with `whitespace-pre-wrap … bg-white p-3` wrapping `{bodyText}`) so the scroll container stays but its inner content is the Markdown view:
```tsx
<div className="max-h-96 overflow-y-auto rounded border bg-white p-3">
  <MarkdownView text={bodyText} />
</div>
```
(Keep the `max-h-96 overflow-y-auto rounded border bg-white p-3` container; only the inner `{bodyText}` text node becomes `<MarkdownView text={bodyText} />`, and drop the now-unneeded `whitespace-pre-wrap text-sm text-slate-700` from that container.)
Leave the 40px truncated preview (`{artifact.body}`) and any error `<span>` exactly as-is.

- [ ] **Step 2: page.tsx — render note bodies**

In `frontend/app/page.tsx`, add the import (match existing component-import path style, e.g. `./components/MarkdownView`).
Replace the note body line:
```tsx
<p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{n.body}</p>
```
with:
```tsx
<MarkdownView className="mt-1" text={n.body} />
```

- [ ] **Step 3: ProfileTab — render the summary**

In `frontend/app/components/ProfileTab.tsx`, add `import MarkdownView from "./MarkdownView";`.
Replace:
```tsx
<p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{profile.summary}</p>
```
with:
```tsx
<MarkdownView className="mt-1" text={profile.summary} />
```
Leave the error `<span className="whitespace-pre-wrap">` (line ~77) untouched.

- [ ] **Step 4: Verify the build compiles**

Run: `npm --prefix frontend run build`
Expected: build succeeds, `frontend/out` regenerated, no type errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components/ArtifactCard.tsx frontend/app/page.tsx frontend/app/components/ProfileTab.tsx
git commit -m "feat(ui): render artifact bodies, notes, and profile summary as markdown"
```
