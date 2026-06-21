# Job Preferences + Decisive Fit-Scoring — Design

> **Attribution:** This adapts the fit-scoring process and preferences concept
> from [proficientlyjobs/proficiently-claude-skills](https://github.com/proficientlyjobs/proficiently-claude-skills)
> (MIT). The original stores preferences in `~/.proficiently/preferences.md`
> and a file-based fit rubric; this project re-implements the *concepts* against
> its own SQLite/MCP architecture and corpus grounding — no text was copied.

## Goal
Give the candidate explicit **job preferences** (dealbreakers / must-haves /
nice-to-haves) and rewrite `fit-analysis` to apply the proficiently
**decisive rubric**: a single dealbreaker → **Skip**; otherwise score must-haves
then nice-to-haves → **High / Medium / Low**. This makes fit scores triage-useful
and feeds the daily-search/weekly-review process engine.

## Storage (project-local — adapts their preferences.md → our DB)
Extend the existing single-row `Profile` (already holds `pinned_skills`,
`target_titles`, `locations` as JSON lists) with three more JSON-list fields:
- `dealbreakers: list[str]` — any present → Skip (agency/crypto, on-site only, no sponsorship, below salary floor, …).
- `must_haves: list[str]` — required criteria.
- `nice_to_haves: list[str]` — bonus criteria.
Migration via `_ensure_column(... JSON DEFAULT '[]')`. `synthesize_profile` does
NOT touch them (user-curated, like `pinned_skills`).

## Service / API
- `profile_service.set_preferences(session, *, dealbreakers=None, must_haves=None, nice_to_haves=None)` — partial, cleaned (trim, dedupe), mirrors `set_pinned_skills`.
- Extend `PATCH /api/corpus/profile` (the existing pinned-skills patch) to accept the three optional lists.

## Fit rubric (rewrite `skills/career-pack/skills/fit-analysis/SKILL.md`)
Adds a preferences-driven rating BEFORE the dimension scores:
1. **Dealbreakers first** — if the opportunity matches ANY dealbreaker, rating =
   **Skip**, state which, and stop scoring dimensions.
2. **Must-haves** — count met; few met → likely **Low**.
3. **Nice-to-haves** — for those passing must-haves.
4. **Rating**: High = no dealbreakers + all must-haves + ≥2 nice-to-haves;
   Medium = no dealbreakers + most must-haves; Low = significant must-have gaps;
   Skip = any dealbreaker.
Then the existing 1–5 dimension table + Strengths/Gaps/Verdict, grounded in the
corpus + profile (anti-fabrication unchanged). The decision row's `summary`
leads with the rating word. Preferences are inlined into the prompt via a new
`preferences_block`.

## Prompt wiring
`Capability` gains `include_preferences: bool = False` (default keeps every other
entry unchanged); `fit-analysis` sets it True. `capabilities.build_prompt` adds a
`preferences_block(profile)` section when the flag is set.

## References (committed, attributed)
`docs/references/fit-scoring.md` and `docs/references/priority-hierarchy.md` —
adapted summaries of the proficiently references for project use, each with the
attribution header. Plus a top-level `ATTRIBUTION.md`.

## UI
`ProfileTab` gains three editable chip-list sections (Dealbreakers / Must-haves /
Nice-to-haves), mirroring the existing pinned-skills editor, saved via the
extended PATCH.

## Testing
- `set_preferences`: partial update, trims/dedupes, leaves other Profile fields
  (incl. `pinned_skills`) intact; `synthesize_profile` doesn't clobber them.
- PATCH `/api/corpus/profile` accepts + returns the three lists.
- `build_prompt` for `fit-analysis` includes a "Preferences" section with the
  dealbreakers/must-haves/nice-to-haves; other capabilities don't.
- `fit-analysis` SKILL.md still passes the static career-pack checks
  (frontmatter name, `## Write-back contract`, `mcp__app__`).
- Frontend `next build`.
Gate green. Constitution III honored — grounding/anti-fabrication unchanged.
