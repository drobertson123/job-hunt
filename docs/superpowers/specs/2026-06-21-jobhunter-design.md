# "Job Hunter" Design — Implementation Design

## Source
The user's own Claude Design project **"Job Hunter"** (`Job Hunter.dc.html`),
imported via the claude_design (DesignSync) MCP. It is a templated design-canvas
mockup (`<x-dc>`/`<sc-for>` bindings); this spec **translates its design language
and shell into the app's React/Tailwind frontend** — not a verbatim copy. It
supersedes the prior TwinForge teal theme.

## Design tokens (extracted from the mockup)
- **Fonts:** Figtree (400/500/600/700) sans; JetBrains Mono (400/500) for
  source/meta/timestamps.
- **Surfaces:** app bg `#f6f4f0` (warm cream); card `#ffffff`; warm panel
  `#fbfaf8`; kanban column `#efeae2`; sunk/tint `#f1ede7`.
- **Lines:** `#ebe7e1` (default), `#e6e0d6`, `#e3ded7`, `#f1ede7` (soft).
- **Ink:** `#211e2b` (primary / dark panels), `#3b3746` (body), `#6c6678`
  (muted), `#9a95a3` (subtle), `#a39c92` (faint).
- **Accent (indigo/purple):** `#5750d9` DEFAULT, `#4840c0` dark (hover),
  `#7a73e6` (2), `#a8a3f0` (3), `#c9c5f2` soft, `#ecebfb` tint (pill bg).
- **Semantic:** green `#3f9a6e` / deep `#2f7a57` (success/automation/active),
  mint `#7ee0b0` (on dark); coral `#d35a4a` (decisions/withdraw); amber `#c98a2e`
  (flags).
- **Dark panel:** `#211e2b` bg, light text (mini-metrics, schedule banner).
- **Radius:** generous — cards 13–16px, buttons/inputs 11px, logo 13px, tags
  6–7px, pills 20px. **Shadow:** soft — card hover `0 8px 22px rgba(33,30,43,.10)`;
  accent button `0 3px 10px rgba(87,80,217,.25)`.

## Shell (replaces TwinForge TopBar + LeftNav + StatusBar)
- **Icon nav rail (76px, white, border-right #ebe7e1):** an accent rounded logo
  (42px, 13px radius, network-dots glyph) at top; a column of **icon buttons**
  (one per primary destination) with tooltips, active = accent-tinted; at the
  bottom a pulsing green "automation active" dot + a 38px dark circular avatar
  with the user's initials. The rail maps to the app's existing canvas
  destinations (board, weekly/this-week, attention, applications, interviews,
  companies, sources, library, profile, workspace) — all stay reachable.
- **Top bar:** a greeting ("Good morning, {name}") + a sub-line with the date and
  "<N> decisions need you today" (N = attention count, coral); a search pill; and
  an accent **Add job** button. Replaces the small TwinForge header. The
  StatusBar is dropped (its counts move into the top bar / rail).
- The existing **chat pane + capability bar** are preserved (restyled to tokens).

## Board (hero screen restyle)
`BoardTab` adopts the mockup's look: warm `#efeae2` kanban columns with colored
headers + counts; white opportunity cards with a left accent stripe, an initials
"logo" chip, company + source (mono), a match/score pill, the role, meta, and a
mono automation note + next-action footer. An **auto-discovery strip** above the
columns (the daily-search status). Where the app shows it, a right **insight
rail** (Needs-your-decision items from attention, automation activity from recent
runs, and a dark **mini-metrics** card: Applied / Response / Active).

## Scope
- IN: token theme + fonts; icon-rail shell + top bar; Board restyle + insight
  rail/mini-metrics; other tabs inherit the tokens.
- OUT (not pixel-rebuilt): the mockup's Contacts/Documents/Relationships/Metrics
  full screens — the app's existing tabs cover this content and inherit the new
  look; a dedicated Metrics screen is a future slice.

## Testing
No frontend unit harness — verification is `npm --prefix frontend run build`
(type-check) + a served-bundle marker check + a visual pass. All canvas
destinations remain reachable (rail keys map 1:1 to the `canvasTab` union).
Backend untouched; gate stays green.
