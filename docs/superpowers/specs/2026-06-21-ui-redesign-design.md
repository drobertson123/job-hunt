# GUI Refresh — Design

## Goal
A better-looking, more usable GUI with **all the same features**. Two concrete
problems with the current UI: (1) twelve cramped, hand-coded flat underline tabs
that overflow and have no grouping; (2) a flat, undifferentiated slate palette
with no visual hierarchy or brand identity.

## Constraint / note
The referenced design system (`claude.ai/design/...`) is auth-gated and returns
403 — it cannot be fetched. This refresh applies standard modern UI principles
(clear hierarchy, one accent color for primary/active affordances, neutral
secondary controls, grouped navigation, generous spacing) rather than copying
that specific system. It is intentionally **shell-scoped** (header, canvas
navigation, chat input, theme accents) so every existing tab inherits the new
look without rewriting tab internals — keeping the change cohesive, low-risk, and
fully feature-preserving.

## Change 1 — Grouped, data-driven canvas navigation
Replace the twelve inline `border-b-2` tab buttons in `page.tsx` with a single
`CanvasNav` component driven by a config array, rendering compact **pill** tabs
in four logical groups separated by thin dividers (wraps gracefully in the
narrow canvas pane):

- **Pipeline:** Board · Detail · Attention · This week
- **Track:** Applications · Interviews · Actions
- **Research:** Companies · Sources · Briefing
- **You:** Workspace · Profile

Active pill = accent (indigo-600) filled; inactive = neutral with hover. Counts
render as small inline badges (board, attention, applications, actions,
companies, workspace) — preserving the existing count affordances. The
render-branch chain below the nav is unchanged; only the nav block is swapped.

## Change 2 — Accent theme + branded header
A single accent (**indigo-600**) for primary/active affordances; neutral slate
for secondary controls (a coherent two-tier system). Specifically:
- Header: a small indigo brand mark + the title + a one-line subtitle.
- Chat **Send** button and primary affordances → indigo; chat input gains an
  indigo focus ring.
- Capability buttons → subtle indigo hover.
- `globals.css` base unchanged except light touches.

## Out of scope (YAGNI)
Per-tab internal restyles (they inherit the theme and keep their slate
secondary controls — a valid accent/neutral split), new features, dark mode,
component libraries.

## Files
- Create `frontend/app/components/CanvasNav.tsx`.
- Modify `frontend/app/page.tsx` (swap nav block; header; chat input/Send;
  capability bar).
- Modify `frontend/app/globals.css` (minor).

## Testing
No frontend unit harness exists — verification is `npm --prefix frontend run
build` (type-check + compile) succeeding, plus a manual visual check. All 12
tabs remain reachable (CanvasNav keys map 1:1 to the existing `canvasTab` union
and render branches); no feature is removed.
