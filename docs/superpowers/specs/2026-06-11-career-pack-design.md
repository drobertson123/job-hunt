# Career Pack — Authored-Skill Seam + Capabilities (Phase 2 slices A+D merged)

**Date:** 2026-06-11
**Status:** Approved design
**Decided with user:** full career pack (A absorbs D), chat + capability endpoint
invocation, auto-grounding on generative kinds, local-plugin packaging.

## Goal

Prove the authored-skill seam with the real thing: a complete career skill pack the
agent discovers via the Claude Agent SDK, invokable from free-form chat and from a
templated capability endpoint, whose outputs land as **structured rows + versioned,
provenance-attributed artifacts** in SQLite. Generative artifacts are automatically
run through the slice-C grounding check.

The master plan's Phase 2 gate applies verbatim: *"the gate is 'correct structured
rows appeared,' not 'a doc rendered'"* — a skill can produce a perfect document and
silently never call the write-back tool, so tests assert rows **and** field values.

## Scope

- **In:** career-pack local plugin (5 skills); runner plugin/skills wiring +
  expanded tool allowlist; `POST /api/capabilities/{name}` + `GET /api/capabilities`;
  post-run auto-grounding of generative artifacts; minimal frontend capability
  buttons + artifact list with kind/review-status badge; offline test suite + one
  live gate.
- **Out:** `.docx`/`.pdf` export and export-time enforcement of `approved`
  (slice E); business-track skills and the MIT-skill normalizer wiring (Phase 3);
  review-queue UI beyond the status badge; scheduled/automatic capability runs.

## 1. Plugin layout + runner changes

```
skills/career-pack/
  .claude-plugin/plugin.json        # {"name": "career-pack", "version": ...}
  skills/
    enrich-opportunity/SKILL.md
    company-research/SKILL.md
    cv-tailor/SKILL.md
    interview-prep/SKILL.md
    fit-analysis/SKILL.md
```

Skills may carry sibling reference files (templates, rubrics) next to their
SKILL.md. Five small skills, not one mega-skill: precise triggering from chat, and
the capability endpoint can name its skill exactly.

`app/agent/runner.py` `build_options()` changes (SDK 0.2.93 verified):

- `plugins=[SdkPluginConfig(type="local", path=str(CAREER_PACK_DIR))]` where
  `CAREER_PACK_DIR` is an **absolute** path derived from the repo/app package
  location — never from the per-run `cwd`. Per-run session-dir isolation is
  untouched; the silent-zero-skills failure mode (project-scope discovery looking
  in an empty session dir) cannot occur.
- `skills=["enrich-opportunity", "company-research", "cv-tailor",
  "interview-prep", "fit-analysis"]`. Per SDK docs this is "the single place to
  turn skills on" — it auto-enables the Skill tool and setting sources;
  `setting_sources` stays `None`.
- `ALLOWED_TOOLS` gains `Skill`, `WebSearch`, `WebFetch` (company research).
  `Read` is deliberately excluded until a skill ships supporting files (then
  re-added scoped to the plugin dir) — unused Read + WebFetch would be an
  exfiltration channel for prompt-injected postings. The `_gate` `can_use_tool`
  callback is unchanged — it already reads the list.

## 2. Skill contracts

Every SKILL.md ends with an explicit **write-back contract** section naming the
`mcp__app__*` tools it MUST call and with what arguments. Per capability:

| Skill | Must call | Artifact kind | Notes |
|---|---|---|---|
| enrich-opportunity | `save_opportunity` (+ `record_action` for the obvious next step) | — | Chat-native sibling of the Phase 1 normalizer; computes `dedupe_key` the same way |
| company-research | `save_artifact` + `save_opportunity` enrichment fields where learned | `research_brief` | Uses `WebSearch`/`WebFetch`; stays `draft` (facts are about the company, not the corpus) |
| cv-tailor | `search_corpus` first, then `save_artifact` | `cv` | Corpus-grounded; auto-grounded → `needs_review` |
| interview-prep | `save_artifact` + `record_action` for prep tasks | `other` (prep doc) | Stays `draft` |
| fit-analysis | `save_artifact` + `record_decision` (kind `choice`, scored rationale) | `fit_analysis` | Re-runnable: new artifact version + new decision row each run |

Grounding rules embedded in the grounded skills (cv-tailor, and any
outreach-flavored output): query `search_corpus` before asserting any fact about
the user; never invent experience; write `[MISSING: …]` for gaps — the same
vocabulary slice C's `annotate` produces, so human reviewers see one convention.

`provenance` is always `"career-pack:<skill-name>"`. `opportunity_id` is passed
through from the invocation prompt where applicable. Versioning is automatic via
`services.add_artifact` (per opportunity/kind/title tuple); approval auto-resets
because new versions are new rows (slice C invariant).

## 3. Capability endpoint + auto-grounding + buttons

**Registry.** `app/capabilities.py` defines the five capabilities: name, skill
name, prompt template, whether `opportunity_id` is required, and whether output
kinds are generative. `GET /api/capabilities` returns it for the UI.

**Invoke.** `POST /api/capabilities/{name}` body `{opportunity_id?: str,
input?: str}` → 404 unknown name, 422 missing required opportunity, 404 unknown
opportunity. It templates a deterministic prompt ("Use the <skill> skill … " with
the opportunity's title/org/url/summary inlined, plus `input` for paste-style
capabilities) and reuses the existing `create_run`/`stream_run` SSE path.
Capability runs are ordinary runs — events persist, re-attach via
`/api/runs/{id}/events`, iteration/budget caps inherited. Free-form chat needs no
endpoint: the skills trigger naturally from `POST /api/chat`.

**Auto-grounding.** After a run's `ResultMessage`, the **runner** (not the skill)
selects artifacts created with that `run_id` whose kind ∈ {`cv`, `cover_letter`,
`pitch`, `outreach`} and calls `run_grounding_check` on each — they land
`needs_review` with findings ready. `research_brief`, `fit_analysis`, and other
kinds stay `draft`. Grounding failure (e.g. missing OpenAI key, empty corpus) is
**non-fatal**: if `run_grounding_check` raises (no key, empty corpus), log it,
persist no report, leave the artifact `draft`; the run still succeeds. This applies to ALL runs (chat and capability) so the gate can't be
bypassed by phrasing.

**Frontend (minimal).** One button per capability (driven by
`GET /api/capabilities`) attached to the opportunity context, posting to the
endpoint and streaming into the existing chat pane. Canvas additionally lists
artifacts with kind + review-status badge (`draft` / `needs_review` / `approved`).
No review-queue UI in this slice.

## 4. Testing + verification

Offline-by-default, existing conventions (fake `query_fn`, injectable embedder,
`_clear_db` autouse fixture):

- **Seam config test:** `build_options()` emits the plugin absolute path, the five
  skill names, and the expanded allowlist; `_gate` still denies unlisted tools.
- **Static pack test:** `plugin.json` parses; exactly the five SKILL.md files
  exist with valid frontmatter whose `name:` matches the directory — a renamed
  skill cannot silently load zero.
- **Write-back tests (the gate):** fake agent emits the tool calls each contract
  requires; assert rows AND field values — artifact kind/provenance/version,
  opportunity fields + dedupe, decision rows, action rows.
- **Auto-grounding tests:** generative-kind artifact from a run → grounding report
  exists + `needs_review`; `research_brief` → stays `draft`; embedder failure →
  run still succeeds, artifact `draft`.
- **Endpoint tests:** registry list; 404/422 validation; prompt templating
  includes opportunity fields; capability run produces events replayable via
  `events_after`.
- **Live gate** (`OH_RUN_LIVE_PROBE=1`, authed `claude` CLI; deliberately no
  OpenAI dependency): seed an opportunity + a profile row, invoke `fit-analysis`
  via the capability path, assert the `fit_analysis` artifact row and
  `record_decision` row appear with correct field values. This is the seam
  proof: real discovery of a repo-local plugin skill from an isolated session
  `cwd`. (fit-analysis scores profile vs opportunity; corpus search is optional
  for it, so the gate avoids needing an embedder key.)

## Risks / notes

- The SDK `skills` option is a context filter, not a sandbox (SDK docstring) —
  fine here; nothing secret lives in skill files.
- `WebSearch`/`WebFetch` make company-research runs network-dependent; the
  offline suite never exercises them live (fake `query_fn` only).
- Auto-grounding threshold remains `OH_GROUNDING_MIN_SIMILARITY` (default 0.40,
  uncalibrated) — calibration is future work, slice C limitation carries over.
- Five-skill triggering precision from free-form chat is unproven until the live
  gate; if chat triggering is flaky, the capability endpoint is the reliable path
  and SKILL.md descriptions get tuned.
- Prompt-injection: pasted postings and fetched pages are untrusted input to a
  tool-bearing agent. Mitigations: tool-name allowlist gate, no Read/Write/Bash,
  single-user local blast radius. Revisit if Read is ever re-added.
