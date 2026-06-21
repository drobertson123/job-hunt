# Markdown Raw/Rendered Views — Design

## Goal
Boxes that display Markdown (artifact bodies, notes, profile summary) currently
render as raw `whitespace-pre-wrap` text. Render them as formatted Markdown, with
a per-box toggle to switch between **Rendered** (default) and **Raw** views.

## Scope (YAGNI)
- **In:** A shared read-only `MarkdownView` component with a Rendered/Raw toggle.
  Applied to the three prose Markdown sites:
  1. `ArtifactCard` expanded body (`bodyText` — the grounded/annotated or raw artifact body)
  2. Workspace notes (`page.tsx`, `n.body`)
  3. `ProfileTab` synthesized summary (`profile.summary`)
- **Out (deferred):** WYSIWYG *editing*. None of these boxes are editable in-app
  today (artifacts are agent-generated and read-only; notes/summary are
  agent-written). Editing is a separate future slice. The artifact 40px preview
  teaser and error message spans stay plain text. Briefing facts are structured
  (key/value), not Markdown — untouched.

## Component: `MarkdownView`
`frontend/app/components/MarkdownView.tsx`

```
type Props = { text: string; className?: string };
```

- Internal `useState` for `mode: "rendered" | "raw"`, default `"rendered"`.
- A small toggle control (two-button segmented `Rendered | Raw`) aligned top-right.
- **Rendered:** `<ReactMarkdown remarkPlugins={[remarkGfm]}>` inside a
  `prose prose-sm max-w-none` wrapper (Tailwind Typography).
- **Raw:** the original `whitespace-pre-wrap` text block (monospace), so the
  user sees exactly the stored Markdown source.
- Empty/whitespace `text` → render nothing (no toggle), so empty notes/summaries
  don't show an empty toolbar.

## Dependencies
- `react-markdown` — renderer (no `dangerouslySetInnerHTML`; safe by default).
- `remark-gfm` — tables, strikethrough, task lists, autolinks.
- `@tailwindcss/typography` — `prose` classes for readable rendered output.
  Added to `frontend/tailwind.config.ts` `plugins: [require("@tailwindcss/typography")]`.

## Data flow / error handling
- Pure presentational; no network. `react-markdown` sanitizes by default
  (raw HTML in source is not executed).
- The grounding `[MISSING: …]` annotations in `annotated_body` are plain text and
  render literally — desired (the reviewer still sees them inline).

## Testing
- No frontend unit-test harness exists; verification is `next build` (type-check +
  compile) plus the existing backend suite via the gate. The component is small,
  presentational, and exercised by the build. (Constitution III/IV: no backend
  behavior changes; grounding/approval pipeline untouched.)
