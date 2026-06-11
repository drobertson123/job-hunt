# Normalizer Probe — Design

**Date:** 2026-06-10
**Phase:** 1 (job track only)
**Status:** Implemented; live gate PASSED 2026-06-11.

## Revision 2026-06-11 — extraction mechanism: CLI session, not the Anthropic API

The original design extracted via the Anthropic API's `messages.parse` structured-output
feature (Approach A's "injectable client"). On review we separated two risks the probe bundles:

- **R1 — extraction:** can an LLM turn messy free-form markdown into correct job-row *values*?
- **R2 — mechanism:** does `messages.parse` / `output_format` hand back a schema-validated
  object without bespoke parse-and-retry glue?

**Decision (user):** build the production reused-skill normalizer on the **local Claude Agent
SDK session** (the same `claude` CLI auth Phase 0 uses) rather than the API — so the app needs
no `ANTHROPIC_API_KEY` for this path. Consequence, taken deliberately: there is **no
structured-output guarantee** (R2 is *not* what we ship), so `normalize_artifact` prompts for a
JSON object matching `NormalizerResult`'s schema and **validates it ourselves with Pydantic**.
This is the inverse of the original "Approach B rejected" note below — the nondeterminism that
note warned about is accepted, and the probe was rebuilt to test *this* (CLI + JSON) path.

`normalize_artifact` is now `async`, injects `query_fn` (mirroring `runner.stream_run`), and
runs a single-turn, tool-less `ClaudeAgentOptions(max_turns=1)` query. The `anthropic`
dependency was removed. The live gate now runs against the local CLI, gated on
`OH_RUN_LIVE_PROBE=1` (no API key), and **passed 2026-06-11**.

## Purpose

De-risk the **reused-skill normalizer seam**, the riskiest seam flagged in the plan.

Reused MIT skills (e.g. the `example.md` career-helper) are *not* written to call our
in-process MCP write-back tools. They emit **free-form markdown artifacts**. To get those
into the system of record, a separate **normalizer** must convert that free-form output into
structured `Opportunity` rows.

This probe pulls one reused skill's free-form artifact through an Anthropic `messages.parse`
normalizer on the **thinnest path** and confirms it yields **correct structured job rows** —
asserting field *values* in SQLite, not merely that a row appeared.

This seam is distinct from the authored-skill seam (`app/agent/tools.py`), where Phase-2
skills call our MCP tools directly. Leaving reused-skill normalization unproven until Phase 3
is the risk this probe retires.

## Success Gate

The probe passes when a representative career-helper research-brief artifact, run through the
normalizer and persisted, produces an `Opportunity` row in SQLite with:

- `type == job`
- non-empty `title`, `organization`, and `summary`
- a stable, deterministic `dedupe_key`

The gate is "correct structured rows appeared," **not** "a document rendered."

## Scope

- **In scope:** the `job` path of the Opportunity schema only.
- **Out of scope:** the `business` path; live agent execution of the reused skill; any UI.
  The `business` track is deferred to Phase 3.

## Approaches Considered

- **A — Standalone normalizer module + injectable client (chosen).**
  New `app/agent/normalizer.py` with a pure `normalize_artifact(markdown, *, client, model)`
  function and a separate `persist_normalized(session, result)` bridge to
  `services.upsert_opportunity`. The client and model are injectable, so the deterministic test
  swaps a fake client — exactly the pattern `runner.py` already uses by injecting `query_fn`.
  Clean seam, independently testable, no coupling to the agent loop.

- **B — Fold normalization into the agent runner.** Rejected. Normalization is a single
  extraction call, not an agent loop. Reusing the agent SDK path re-introduces the local
  `claude` CLI subprocess dependency and nondeterminism that the probe is meant to avoid.

- **C — One-off throwaway script.** Rejected. Fastest to write, but leaves no reusable module
  for Phase 3 and no regression guard.

## Architecture (Approach A)

```
tests/fixtures/career_helper_research_brief.md   <- representative free-form artifact (committed)
        |
        v
app/agent/normalizer.py
  |- Pydantic output schema:
  |     NormalizerResult { opportunities: list[NormalizedJob] }
  |     NormalizedJob   { title, organization, url, location,
  |                       summary, source, dedupe_key, details: dict }
  |
  |- normalize_artifact(markdown, *, client=None, model=None) -> NormalizerResult
  |     client.messages.parse(model=..., max_tokens=..., messages=[...],
  |                           output_format=NormalizerResult)
  |     returns response.parsed_output
  |     model resolved via settings_service (UI override wins) -> default claude-sonnet-4-6
  |
  |- persist_normalized(session, result, *, source) -> list[Opportunity]
        for each opportunity -> services.upsert_opportunity(type=job, ...)
```

## Components & Data Flow

1. **Fixture** — `tests/fixtures/career_helper_research_brief.md`. One committed research brief
   covering a single company + role, in the shape the career-helper skill emits. Deterministic
   input; no live skill run. (Note: `example.md` references a `templates/` directory that does
   not exist locally, so a live run would not produce its intended templated shape anyway — a
   captured fixture is both thinner and more representative.)

2. **Schema** — `NormalizedJob` fields map 1:1 onto `services.upsert_opportunity`'s keyword
   arguments. `details` is a free JSON dict (the `Opportunity.details` column is JSON), carrying
   job-specific extras such as compensation, seniority, and key requirements. A list wrapper
   (`NormalizerResult.opportunities`) allows 0..n rows; the fixture yields exactly one.

3. **`normalize_artifact(markdown, *, client=None, model=None)`** — a single
   `client.messages.parse(...)` call with `output_format=NormalizerResult`, returning the
   validated instance via `response.parsed_output`. `client` defaults to a real
   `anthropic.Anthropic()` but is injectable for the stubbed test. `model` resolves through the
   existing settings layer (`app.settings_service`), defaulting to `claude-sonnet-4-6`.

4. **`persist_normalized(session, result, *, source)`** — maps each `NormalizedJob` to
   `services.upsert_opportunity(type=job, ...)` and returns the persisted rows. `dedupe_key`
   defaults to a stable slug derived from organization + title when the model does not supply one.

## Testing (both layers)

- **Live probe** — `tests/test_normalizer_probe.py`, marked
  `@pytest.mark.skipif(no ANTHROPIC_API_KEY)`. Calls the real `messages.parse` on the fixture,
  persists, and asserts the DB row satisfies the Success Gate. This is the genuine de-risking;
  it auto-skips on a keyless CI run rather than failing.

- **Stubbed plumbing** — same test module. Injects a fake client returning a canned
  `NormalizerResult`, persists, and asserts the row mapping. Fast, keyless, deterministic
  regression guard for the object -> `upsert_opportunity` -> DB-row path.

## Other Decisions

- **Dependency:** add `anthropic` (`uv add anthropic`). Currently only `claude-agent-sdk` is
  installed, which does not pull in `anthropic`.
- **Model:** default `claude-sonnet-4-6` — supports structured outputs and is cheap — overridable
  via the `settings` table (UI-entered overrides win over env, per `app.settings_service`).
- **Module location:** `app/agent/normalizer.py`, alongside the existing agent seam code.

## Out of Scope / YAGNI

- No business-track normalization.
- No live agent run of the reused skill.
- No retry/batching logic — single artifact, single call.
- No UI wiring; the probe is exercised through tests only.
