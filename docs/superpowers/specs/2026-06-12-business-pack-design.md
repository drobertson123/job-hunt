# Business Pack — authored business skills (Phase 3 slice F)

**Date:** 2026-06-12
**Status:** Implemented (plan docs/superpowers/plans/2026-06-12-business-pack.md); live gate PASSED 2026-06-12 (real CLI session with both plugins discovered business-pack:qualify-opportunity and followed its contract, 38s)
**Decided with user:** Phase 3 decomposed F (business pack) → G (reused MIT
components + normalizer breadth) → H (cross-domain rubric); F first. Four
capabilities; `proposal` stays UNGATED (user decision — internal working doc;
only the existing GENERATIVE_KINDS stay review-gated). Approach: second plugin
+ shared registry with a `plugin` field.

## Goal

The business track gets its authored pack on the architecture slice A+D
proved: a repo-local `business-pack` plugin whose four skills follow
write-back contracts into the same schema (opportunities with
`type="business"`, artifacts, actions, decisions), invokable from chat and
the capability endpoint, with zero new UI work.

## Scope

- **In:** `skills/business-pack/` plugin (4 skills); `Capability.plugin`
  field + 4 registry entries; `business_pack_dir` config; runner passes both
  plugin paths (derived from the registry, not hardcoded); static/contract/
  endpoint tests; one live gate (qualify-opportunity).
- **Out:** reused MIT skills + business normalizer breadth (slice G);
  cross-domain rubric (slice H); scheduled discovery sweeps (Future);
  changes to GENERATIVE_KINDS, export, grounding, or frontend.

## 1. Plugin layout + runner/config

```
skills/business-pack/
  .claude-plugin/plugin.json        # {"name": "business-pack", ...}
  skills/
    discover-opportunities/SKILL.md
    qualify-opportunity/SKILL.md
    analyze-opportunity/SKILL.md
    draft-pursuit/SKILL.md
```

- `AppConfig.business_pack_dir: Path = ROOT_DIR / "skills" / "business-pack"`
  (absolute, sibling of `career_pack_dir`).
- The runner builds
  `plugins=[{"type": "local", "path": str(p)} for p in (cfg.career_pack_dir, cfg.business_pack_dir)]`
  — two explicit config fields, no dynamic discovery (YAGNI). The registry
  stays the single source of truth for skill NAMES; config owns plugin PATHS.
- `ALLOWED_TOOLS` unchanged: discover-opportunities uses the already-allowed
  `WebSearch`/`WebFetch`; everything else is `mcp__app__*` + `Skill`.

## 2. Registry generalization

- `Capability` dataclass gains `plugin: str`. The five existing career
  entries set `plugin="career-pack"` — no behavior change.
- `SKILL_NAMES = [f"{c.plugin}:{c.skill}" for c in CAPABILITIES]` (now 9).
- New entries (name == skill dir, as before):

| name | requires_opportunity | requires_input | include_profile | plugin |
|---|---|---|---|---|
| discover-opportunities | no | no (optional focus text) | yes | business-pack |
| qualify-opportunity | yes | no | yes | business-pack |
| analyze-opportunity | yes | no | no | business-pack |
| draft-pursuit | yes | no (optional angle/ask) | yes | business-pack |

- `build_prompt` unchanged — opportunity/profile/input blocks work as-is.

## 3. Skill contracts

Every SKILL.md ends with `## Write-back contract (MUST)`:

| Skill | Must call | Notes |
|---|---|---|
| discover-opportunities | `save_opportunity` per distinct find + one `record_action` | `type="business"`, `source="discovery"`, `dedupe_key` = URL else `<org>|<title>` lowercased, `details.opportunity_kind` ∈ rfp\|grant\|startup\|fractional\|partnership, plus stated `value_estimate`/`deadline` only; **≤10 per sweep**; action = "Triage discovered opportunities", `kind="research"` |
| qualify-opportunity | `update_pipeline_status` + `record_decision` | stage from evidence (`qualifying`→`analyzing`/`active` or `lost`), rationale required; decision `kind="choice"`, summary "Qualified <title>: <verdict>" |
| analyze-opportunity | `save_artifact` + `record_action` (≤3) | kind `research_brief`, title "Analysis — <title>", provenance `business-pack:analyze-opportunity`; sections: opportunity shape, market/competition, effort vs value, risks, verdict; stays `draft` |
| draft-pursuit | `search_corpus` first, then `save_artifact` | corpus-grounded like cv-tailor: never invent capabilities/experience, `[MISSING: …]` for gaps; kind `outreach` (review-gated → auto-grounded → needs_review) for messages, `proposal` (ungated — user decision) for proposal docs, picked from what the user asked; title "<Outreach|Proposal> — <organization>", provenance `business-pack:draft-pursuit` |

Web research (discover): cite the source URL per find; never fabricate an
opportunity that has no URL/source — skip instead.

`GENERATIVE_KINDS` is untouched: `outreach` was already gated; `proposal`
deliberately is not.

## 4. Testing + verification

- **Static pack tests** (extend `tests/test_career_pack.py` patterns into a
  parameterized form or a sibling `tests/test_business_pack.py`): manifest
  parses, exactly the 4 expected skill dirs, frontmatter name == dir,
  write-back contract section present.
- **Registry tests:** 9 capabilities total; business `.skill` values match
  the pack dirs; `SKILL_NAMES` contains `business-pack:qualify-opportunity`
  etc.; career names unchanged (regression).
- **Runner test:** `build_options` emits BOTH plugin paths and all 9
  qualified names.
- **Write-back contract tests** (extend `tests/test_write_back_contracts.py`):
  discover shape — two `save_opportunity` calls with distinct dedupe_keys →
  two business rows with `source="discovery"` + `details.opportunity_kind`;
  re-save same dedupe_key updates not duplicates. Qualify shape —
  `update_pipeline_status` + `record_decision` → stage changed, Decision row
  with rationale. (analyze/draft-pursuit reuse save_artifact paths already
  contract-tested in slice A+D.)
- **Endpoint tests:** the 4 new names validate via the registry (422 missing
  opportunity_id for qualify, 200 list shows 9, templated prompt contains
  `business-pack:qualify-opportunity` + opportunity block).
- **Live gate** (`OH_RUN_LIVE_PROBE=1`, authed CLI, no web/no OpenAI key):
  seed a `business` opportunity (stage `qualifying`) + profile; invoke
  qualify-opportunity via `caps.build_prompt` + `runner.stream_run`; assert
  the stage CHANGED from `qualifying` and a Decision row with non-empty
  rationale exists. Proves discovery of the second plugin.
- **Frontend:** zero changes — buttons render from `GET /api/capabilities`.
  Verify by `npm run build` only.

## Risks / notes

- discover-opportunities output quality depends on WebSearch results; the
  ≤10 cap and the no-URL-no-row rule bound the junk. Scheduled sweeps remain
  future work.
- Two plugins, nine skills: chat-trigger precision may degrade as the skill
  list grows; the capability endpoint remains the reliable path (same
  trade-off accepted in slice A+D).
- `proposal` ungated is a deliberate user decision; if proposals start going
  out the door unreviewed and that bites, the fix is one membership change in
  `GENERATIVE_KINDS` (both gates update together).
- Business `details` fields follow the documented convention in
  `app/models.py` (`opportunity_kind`, `value_estimate`, `deadline`) — no
  schema change in this slice.
