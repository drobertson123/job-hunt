# Adopt the TwinForge Design Language — Design

## Goal
Re-skin Opportunity Hunter to the **TwinForge Design Language** (provided in
`.design/`), keeping all features. The tokens in `.design/TwinForge Design
Language.html` / the `TF` object are the authoritative contract — match them
exactly, translated into our Tailwind/React idiom.

## Design tokens (the `TF` contract)
Translate into the Tailwind theme (named colors + font families + radius +
shadow) and CSS:

**Colors** — surfaces `bg #f5f6f7 · surface #fff · surfaceAlt #fafbfc ·
surfaceSunk #edeef0`; lines `line #d8dbe0 · lineSoft #e8eaee · lineStrong
#b5bac2`; text `ink #0f1620 · inkMuted #5a6270 · inkSubtle #8a929e`; **accent =
deep teal `#0f766e` / accentSoft `#e6f2f0` / accentInk `#0a4f49`** (rare,
brand + primary actions only — explicitly NOT SaaS-blue); semantic conformance
vocabulary `ok #2f7d4e/okSoft · override #3b7bb8/overrideSoft · warn (umber)
#b45816/warnSoft · error #a6342a/errorSoft · stale #7a8494/staleSoft`.

**Type** — sans **Inter** (400/500/600/700), mono **JetBrains Mono**. Scale:
micro 10.5/600/+0.6 UPPERCASE; caption 11/500; body 12.5/400; bodyB 12.5/600;
title 15/600/−0.15; h 18/600; xh 22/600. **Radius** tight: xs 2 · sm 3 · md 4 ·
lg 6. **Spacing** 4px base. **Elevation** flat — borders over shadows; `panel
0 1px 0 rgba(15,22,32,.04)`, `pop`, `modal` only for popovers/modals.

**Principles** (binding): color is semantic not decorative; accent is rare;
warn is umber not yellow; flat over shadowed; tight industrial radius; mono for
identifiers (opportunity IDs, URLs, dedupe keys).

## Primitives (`frontend/app/components/ui/`)
Ported 1:1 from `.design/app-shell.jsx`, as Tailwind/React components:
- `Pill({ tone, size, mono, solid })` — tones neutral/accent/ok/override/warn/
  error/stale; sm/md; radius sm; 11px/600.
- `Button({ kind, size, icon })` — primary (teal) / ghost / outline / danger;
  sm/md; radius sm; 1px border.
- `Panel({ title, actions, children })` — surface, 1px line border, radius sm,
  surfaceAlt header strip with a micro UPPERCASE title.
- `IconBtn({ title })` — 26px square, radius sm.

## Shell — adopt the AppShell pattern
Restructure `page.tsx` from `header + (chat | canvas-with-top-tabs)` into the
TwinForge AppShell:

```
TopBar (44px): teal logo mark + "Opportunity Hunter" + SettingsBadge
+----------+----------------------------+----------------------------+
| LeftNav  | Chat pane                  | Canvas content             |
| (220px)  | (capability bar + thread   | (the active tab's content; |
| sectioned|  + input)                  |  NO top tab strip anymore) |
| nav      |                            |                            |
+----------+----------------------------+----------------------------+
StatusBar (24px, mono): live counts (opps · applications · actions · attention)
```

- **LeftNav (220px)** replaces the horizontal `CanvasNav`. Sectioned exactly
  like TwinForge: micro UPPERCASE group labels + items; active item =
  `accentSoft` bg + 2px left `accent` rule + `ink`/600; inactive = `inkMuted`/500
  hover `surfaceSunk`; trailing count `Pill`. Groups:
  **Pipeline** (Board · Detail · Attention · This week) ·
  **Track** (Applications · Interviews · Actions) ·
  **Research** (Companies · Sources · Briefing) ·
  **You** (Workspace · Profile).
- **TopBar (44px):** teal rounded logo mark (inset white square, like TF) +
  title + the existing `SettingsBadge`.
- **StatusBar (24px):** mono footer with live counts and an app version.
- Chat pane + capability bar + canvas container retheme to tokens: capability
  buttons → ghost `Button`s; Send → primary `Button`; input → `line` border +
  `accent` focus ring; messages well → `surfaceSunk`.

## Accent-consistency pass (tab internals)
Tab components keep their neutral slate (a fine stand-in for TF grays), but every
**accent-bearing** affordance is unified to teal: swap leftover `bg-slate-900`
primary buttons and any `indigo-*`/`rounded-full` from the prior refresh →
`accent`. Status badges (pipeline stage, attention, action kind) use `Pill`
tones where the mapping is clean (won→ok, attention/overdue→warn/error,
stale→stale). Opportunity IDs / URLs render in mono. This pass is bounded to
accent/active/primary classes — neutral text/borders stay.

## Out of scope
TwinForge's domain screens (Class Editor, Reconcile, DTDL graph, multi-window) —
those are its product, not ours. We adopt the *language* (tokens, primitives,
shell), not those screens. No new features.

## Testing
No frontend unit harness — verification is `npm --prefix frontend run build`
(type-check + compile) + a manual visual check. All 12 nav destinations remain
reachable (LeftNav keys map 1:1 to the `canvasTab` union + render branches).
Fonts loaded via Google Fonts `@import`. Backend untouched; gate stays green.
