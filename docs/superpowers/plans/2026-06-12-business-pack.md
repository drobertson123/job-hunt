# Business Pack Implementation Plan (Phase 3 slice F)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Author the business-pack plugin (4 skills) on the proven career-pack architecture: registry-driven capabilities, write-back contracts, both plugins discovered by the runner, live gate on qualify-opportunity.

**Architecture:** A second repo-local SDK plugin `skills/business-pack/`. The capability registry (`app/capabilities.py`) gains a `plugin` field per entry; `SKILL_NAMES` and `build_prompt` derive `<plugin>:<skill>` from it. The runner passes both absolute plugin paths from two config fields. No frontend, schema, grounding, or export changes — `GENERATIVE_KINDS` is untouched (`outreach` already gated; `proposal` deliberately not, per user decision).

**Tech Stack:** claude-agent-sdk 0.2.93 plugins, FastAPI, pytest offline (fake `query_fn`), one live CLI gate.

**Spec:** `docs/superpowers/specs/2026-06-12-business-pack-design.md`

**Branch:** create `feature/phase3-business-pack` from `main` before Task 1.

**Conventions:** `uv run pytest` (never bare pytest). The suite currently sits at 137 passed / 3 skipped.

---

### Task 1: Business-pack plugin (manifest + 4 SKILL.md) with static validity tests

**Files:**
- Test: `tests/test_business_pack.py`
- Create: `skills/business-pack/.claude-plugin/plugin.json`
- Create: `skills/business-pack/skills/discover-opportunities/SKILL.md`
- Create: `skills/business-pack/skills/qualify-opportunity/SKILL.md`
- Create: `skills/business-pack/skills/analyze-opportunity/SKILL.md`
- Create: `skills/business-pack/skills/draft-pursuit/SKILL.md`

- [ ] **Step 1: Write the failing static tests**

Create `tests/test_business_pack.py`:

```python
"""Static validity of the business-pack plugin (mirror of test_career_pack.py).

A renamed/missing skill must fail loudly here — the SDK would otherwise just
discover zero skills and the agent would silently improvise.
"""

from __future__ import annotations

import json
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parent.parent / "skills" / "business-pack"
EXPECTED_SKILLS = {
    "discover-opportunities",
    "qualify-opportunity",
    "analyze-opportunity",
    "draft-pursuit",
}


def test_plugin_manifest_parses():
    manifest = json.loads((PACK_DIR / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "business-pack"
    assert manifest["description"]


def test_exactly_the_expected_skills_exist():
    found = {p.name for p in (PACK_DIR / "skills").iterdir() if p.is_dir()}
    assert found == EXPECTED_SKILLS


def _frontmatter(skill_dir: Path) -> dict[str, str]:
    text = (skill_dir / "SKILL.md").read_text()
    assert text.startswith("---\n"), f"{skill_dir.name}: missing frontmatter"
    block = text.split("---", 2)[1]
    return {
        k.strip(): v.strip()
        for k, v in (line.split(":", 1) for line in block.strip().splitlines() if ":" in line)
    }


def test_skill_frontmatter_matches_directory():
    for skill_dir in sorted((PACK_DIR / "skills").iterdir()):
        meta = _frontmatter(skill_dir)
        assert meta["name"] == skill_dir.name
        assert meta["description"], f"{skill_dir.name}: empty description"


def test_every_skill_declares_a_write_back_contract():
    for skill_dir in sorted((PACK_DIR / "skills").iterdir()):
        body = (skill_dir / "SKILL.md").read_text()
        assert "## Write-back contract" in body, skill_dir.name
        assert "mcp__app__" in body, skill_dir.name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_business_pack.py -v`
Expected: FAIL (FileNotFoundError — `skills/business-pack` does not exist).

- [ ] **Step 3: Create the plugin manifest**

Create `skills/business-pack/.claude-plugin/plugin.json`:

```json
{
  "name": "business-pack",
  "description": "Opportunity Hunter authored business skills: discovery sweeps, qualification, analysis, pursuit drafting.",
  "version": "0.1.0"
}
```

- [ ] **Step 4: Create the four SKILL.md files**

Create `skills/business-pack/skills/discover-opportunities/SKILL.md`:

```markdown
---
name: discover-opportunities
description: Use when the user asks to find or discover business opportunities — RFPs, grants, consulting or fractional leads, startup angles — via web search matched to their profile. Saves structured opportunity rows.
---

# Discover Opportunities

Sweep the web for concrete business opportunities matching the candidate
profile. Quality over quantity: a row with no source URL is worse than no
row — never fabricate an opportunity.

## Steps

1. Read the Candidate profile block (skills, target titles, locations) and
   the optional Input block (a focus, e.g. "grants for ML tooling").
2. Use `WebSearch` (and `WebFetch` to confirm promising hits) to find LIVE
   opportunities: RFPs, grants, consulting/fractional leads, partnership or
   startup angles. Prefer sources with deadlines and concrete asks.
3. Keep at most the 10 best matches. Skip anything you cannot source to a
   URL.
4. For each kept find, call `mcp__app__save_opportunity` (contract below).
5. Call `mcp__app__record_action` once (contract below).
6. Reply with a ranked one-line-per-find summary.

## Write-back contract (MUST)

- `mcp__app__save_opportunity` per distinct find with: `type="business"`,
  `title`, `organization`, `url` (the source — REQUIRED), `summary` (2-3
  sentences including why it matches the profile), `source="discovery"`,
  `dedupe_key` = the URL, `details` containing `opportunity_kind` (one of
  `rfp|grant|startup|fractional|partnership`) plus `value_estimate` /
  `deadline` ONLY when the source states them.
- Maximum 10 `save_opportunity` calls per sweep.
- `mcp__app__record_action` once with:
  `title="Triage discovered opportunities"`, `kind="research"`.

Do NOT save an artifact; this capability produces structured rows only.
```

Create `skills/business-pack/skills/qualify-opportunity/SKILL.md`:

```markdown
---
name: qualify-opportunity
description: Use when the user asks to qualify, triage, or decide whether to pursue a business opportunity — moves its pipeline stage with evidence and records the decision.
---

# Qualify Opportunity

Decide whether one business opportunity deserves pursuit. Be honest: the
pipeline only works if `lost` is used freely. Evidence over enthusiasm.

## Steps

1. Read the Opportunity block (including `details`: opportunity_kind,
   value_estimate, deadline) and the Candidate profile block.
2. Assess: capability fit (can the candidate credibly deliver?), effort vs
   value, timing/deadline feasibility, competition/odds.
3. Pick the new stage: `analyzing` (promising, needs a deep dive), `active`
   (clear yes, start pursuing), or `lost` (pass — say why). Never leave it
   at `qualifying`.
4. Call `mcp__app__update_pipeline_status` then `mcp__app__record_decision`
   (contract below).
5. Reply with the verdict and the 2-3 decisive reasons.

## Write-back contract (MUST)

- `mcp__app__update_pipeline_status` with: `opportunity_id` from the
  Opportunity block, `stage` from step 3, `rationale` (required — the
  decisive evidence).
- `mcp__app__record_decision` with:
  `summary="Qualified <title>: <verdict>"`, `kind="choice"`,
  `opportunity_id`, `rationale` = the 2-3 decisive reasons.

Do NOT save an artifact; this capability produces structured rows only.
```

Create `skills/business-pack/skills/analyze-opportunity/SKILL.md`:

```markdown
---
name: analyze-opportunity
description: Use when the user asks for a deep analysis of a business opportunity — market, competition, effort vs value, risks — saved as a research-brief artifact plus next-step actions.
---

# Analyze Opportunity

Produce a decision-grade analysis brief for one business opportunity. Use
`WebSearch`/`WebFetch` where public facts help; write `[MISSING: <what you
looked for>]` for anything you could not verify rather than guessing.

## Steps

1. Read the Opportunity block (including `details`).
2. Research what is verifiable: the organization, the market, comparable
   deals/awards, typical terms for this `opportunity_kind`.
3. Write the brief in markdown with sections: `## Opportunity shape`,
   `## Market & competition`, `## Effort vs value`, `## Risks`,
   `## Verdict & next steps`, `## Sources` (URLs).
4. Call `mcp__app__save_artifact` (contract below).
5. Call `mcp__app__record_action` for the concrete next steps (max 3).
6. Reply with the verdict paragraph.

## Write-back contract (MUST)

- `mcp__app__save_artifact` with: `title="Analysis — <title>"`,
  `kind="research_brief"`, `opportunity_id` from the Opportunity block,
  `provenance="business-pack:analyze-opportunity"`, `body` = the full
  markdown brief.
- `mcp__app__record_action` per next step (max 3), `kind="research"` or
  `kind="followup"`, linked to the opportunity.
```

Create `skills/business-pack/skills/draft-pursuit/SKILL.md`:

```markdown
---
name: draft-pursuit
description: Use when the user asks to draft outreach or a proposal for a business opportunity — corpus-grounded, never inventing capabilities or experience.
---

# Draft Pursuit (outreach / proposal)

Draft the document that opens or advances a business pursuit. It asserts the
candidate's capabilities to an external party — the grounding rules are
non-negotiable.

## Grounding rules (non-negotiable)

- Call `mcp__app__search_corpus` for every capability claim you plan to make
  (at least 2 queries) before writing.
- Every capability, past result, metric, and client reference MUST come from
  a corpus passage or the Candidate profile block; write
  `[MISSING: <the thing>]` instead of inventing.

## Steps

1. Read the Opportunity block, Candidate profile block, and optional Input
   block (angle, ask, constraints).
2. Decide the form from the user's ask: a short outreach MESSAGE
   (intro/pitch email) or a PROPOSAL document (scope, approach,
   deliverables, timeline; pricing only if the user gave numbers). Default
   to outreach for a first contact.
3. Run the corpus searches (grounding rules above).
4. Draft it — tight, specific to this opportunity, no generic filler.
5. Call `mcp__app__save_artifact` (contract below).
6. Reply with the draft's key angle and any `[MISSING: …]` gaps.

## Write-back contract (MUST)

- `mcp__app__save_artifact` with `opportunity_id` from the Opportunity
  block, `provenance="business-pack:draft-pursuit"`, `body` = the full
  markdown, and:
  - outreach message → `title="Outreach — <organization>"`,
    `kind="outreach"` (it will be auto-checked and land in review as
    `needs_review` — that is expected; do not try to approve it);
  - proposal document → `title="Proposal — <organization>"`,
    `kind="proposal"`.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_business_pack.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add skills/business-pack/ tests/test_business_pack.py
git commit -m "feat(skills): business-pack plugin — 4 authored skills with write-back contracts"
```

---

### Task 2: Registry generalization — `Capability.plugin` + 4 business entries

**Files:**
- Modify: `tests/test_capabilities.py`
- Modify: `app/capabilities.py`

- [ ] **Step 1: Update/extend the tests (failing first)**

In `tests/test_capabilities.py`:

1. Add a second pack-dir constant after `PACK_SKILLS_DIR`:

```python
BUSINESS_SKILLS_DIR = (
    Path(__file__).resolve().parent.parent / "skills" / "business-pack" / "skills"
)
```

2. REPLACE `test_registry_has_the_five_capabilities` with:

```python
def test_registry_has_the_expected_capabilities():
    assert set(caps.REGISTRY) == {
        # career-pack (slice A+D)
        "enrich-opportunity",
        "company-research",
        "cv-tailor",
        "interview-prep",
        "fit-analysis",
        # business-pack (slice F)
        "discover-opportunities",
        "qualify-opportunity",
        "analyze-opportunity",
        "draft-pursuit",
    }
```

3. REPLACE `test_registry_skills_match_pack_directories` with:

```python
def test_registry_skills_match_pack_directories():
    career_dirs = {p.name for p in PACK_SKILLS_DIR.iterdir() if p.is_dir()}
    business_dirs = {p.name for p in BUSINESS_SKILLS_DIR.iterdir() if p.is_dir()}
    assert {c.skill for c in caps.CAPABILITIES if c.plugin == "career-pack"} == career_dirs
    assert {c.skill for c in caps.CAPABILITIES if c.plugin == "business-pack"} == business_dirs
```

4. REPLACE `test_skill_names_are_plugin_qualified` with:

```python
def test_skill_names_are_plugin_qualified():
    assert len(caps.SKILL_NAMES) == 9
    assert "career-pack:fit-analysis" in caps.SKILL_NAMES
    assert "business-pack:qualify-opportunity" in caps.SKILL_NAMES
```

5. APPEND a prompt test for a business capability:

```python
def test_build_prompt_uses_capability_plugin():
    cap = caps.REGISTRY["qualify-opportunity"]
    opp = Opportunity(
        type=OpportunityType.business, title="ML tooling grant",
        organization="GrantCo", dedupe_key="https://grants.example/ml",
        details={"opportunity_kind": "grant", "deadline": "2026-07-01"},
    )
    prompt = caps.build_prompt(cap, opportunity=opp, profile=None)
    assert '"business-pack:qualify-opportunity"' in prompt
    assert "ML tooling grant" in prompt
    assert '"opportunity_kind": "grant"' in prompt  # details JSON survives
    assert "Candidate profile" in prompt  # include_profile=True, placeholder when None
```

(The three existing `build_prompt` tests stay unchanged — career entries keep
working because `plugin="career-pack"` produces the same qualified names.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_capabilities.py -v`
Expected: FAIL (`Capability.__init__` has no `plugin`; registry has 5 names)

- [ ] **Step 3: Generalize the registry**

In `app/capabilities.py`:

1. Update the module docstring's first line to:
   `"""Capability registry — named, templated invocations of authored-pack skills.`

2. Replace the `PLUGIN_NAME = "career-pack"` constant with:

```python
CAREER_PLUGIN = "career-pack"
BUSINESS_PLUGIN = "business-pack"
```

3. Add the field to the dataclass (after `include_profile`):

```python
    plugin: str  # which authored pack ships the skill (qualified name prefix)
```

4. Add `plugin=CAREER_PLUGIN,` as the last argument of each of the five
   existing career entries.

5. Append the four business entries to `CAPABILITIES`:

```python
    Capability(
        name="discover-opportunities",
        skill="discover-opportunities",
        label="Discover",
        description="Web sweep for business opportunities (RFPs, grants, leads) matching your profile.",
        requires_opportunity=False,
        requires_input=False,
        include_profile=True,
        plugin=BUSINESS_PLUGIN,
    ),
    Capability(
        name="qualify-opportunity",
        skill="qualify-opportunity",
        label="Qualify",
        description="Qualify a business opportunity: move its stage with evidence and record the decision.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=True,
        plugin=BUSINESS_PLUGIN,
    ),
    Capability(
        name="analyze-opportunity",
        skill="analyze-opportunity",
        label="Analyze",
        description="Decision-grade analysis brief: market, competition, effort vs value, risks.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=False,
        plugin=BUSINESS_PLUGIN,
    ),
    Capability(
        name="draft-pursuit",
        skill="draft-pursuit",
        label="Draft pursuit",
        description="Corpus-grounded outreach message or proposal for a business opportunity.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=True,
        plugin=BUSINESS_PLUGIN,
    ),
```

6. Re-derive the qualified names from the entries:

```python
# Plugin-qualified names for ClaudeAgentOptions.skills.
SKILL_NAMES = [f"{c.plugin}:{c.skill}" for c in CAPABILITIES]
```

7. In `build_prompt`, change the first element of `parts` to use the
   capability's plugin:

```python
    parts = [
        f'Use the "{cap.plugin}:{cap.skill}" skill now (via the Skill tool), '
        "then follow its write-back contract exactly."
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_capabilities.py tests/test_career_pack.py tests/test_business_pack.py -v`
Expected: all PASS (career-pack tests unaffected: same qualified names emerge)

- [ ] **Step 5: Commit**

```bash
git add app/capabilities.py tests/test_capabilities.py
git commit -m "feat(capabilities): per-capability plugin field + 4 business-pack entries"
```

---

### Task 3: Config + runner — discover BOTH plugins

**Files:**
- Modify: `tests/test_career_pack.py` (the build_options test)
- Modify: `app/config.py`
- Modify: `app/agent/runner.py`

- [ ] **Step 1: Update the seam test (failing first)**

In `tests/test_career_pack.py`, REPLACE `test_build_options_enables_career_pack` with:

```python
def test_build_options_enables_both_packs(tmp_path):
    opts = runner.build_options(model=None, cwd=tmp_path, api_key=None)
    cfg = get_config()
    assert cfg.career_pack_dir.is_absolute()
    assert cfg.business_pack_dir.is_absolute()
    assert opts.plugins == [
        {"type": "local", "path": str(cfg.career_pack_dir)},
        {"type": "local", "path": str(cfg.business_pack_dir)},
    ]
    assert opts.skills == caps.SKILL_NAMES
    assert len(opts.skills) == 9
    for name in ("Skill", "WebSearch", "WebFetch"):
        assert name in opts.allowed_tools
    assert all(t in opts.allowed_tools for t in ALL_TOOL_NAMES)
    # both plugin paths must point at real packs (not depend on cwd)
    assert (cfg.career_pack_dir / ".claude-plugin" / "plugin.json").exists()
    assert (cfg.business_pack_dir / ".claude-plugin" / "plugin.json").exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_career_pack.py -v`
Expected: the replaced test FAILS (`AppConfig` has no `business_pack_dir`); others PASS.

- [ ] **Step 3: Add the config field**

In `app/config.py`, directly after the `career_pack_dir` field, add:

```python
    business_pack_dir: Path = ROOT_DIR / "skills" / "business-pack"
```

(The comment above `career_pack_dir` about absolute paths covers both.)

- [ ] **Step 4: Wire the runner**

In `app/agent/runner.py` `build_options`, replace the single-plugin line:

```python
        plugins=[{"type": "local", "path": str(cfg.career_pack_dir)}],
```

with:

```python
        plugins=[
            {"type": "local", "path": str(p)}
            for p in (cfg.career_pack_dir, cfg.business_pack_dir)
        ],
```

and update the comment above it from "a repo-local plugin" to "repo-local
plugins" (the rest of the comment stands).

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_career_pack.py tests/test_business_pack.py tests/test_capabilities.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add app/config.py app/agent/runner.py tests/test_career_pack.py
git commit -m "feat(runner): discover business-pack alongside career-pack (both absolute paths)"
```

---

### Task 4: Write-back contract tests (discover + qualify shapes)

The two business-specific row shapes. (analyze/draft-pursuit reuse
`save_artifact` paths already contract-tested in slice A+D.)

**Files:**
- Modify: `tests/test_write_back_contracts.py`

- [ ] **Step 1: Extend imports and append the tests**

In `tests/test_write_back_contracts.py`:

1. Extend the tools import with `update_pipeline_status`:

```python
from app.agent.tools import (
    current_run_id,
    record_action,
    record_decision,
    save_artifact,
    save_opportunity,
    update_pipeline_status,
)
```

2. Extend the models import with `OpportunityType` and `PipelineStage` (add
   both names to the existing `from app.models import (...)` block).

3. Append:

```python
async def test_discover_contract_rows_and_dedupe(run_ctx):
    for suffix in ("a", "b"):
        await save_opportunity.handler({
            "type": "business",
            "title": f"Grant {suffix}",
            "organization": "GrantCo",
            "url": f"https://grants.example/{suffix}",
            "summary": "Matches profile: ML platform work.",
            "source": "discovery",
            "dedupe_key": f"https://grants.example/{suffix}",
            "details": {"opportunity_kind": "grant", "deadline": "2026-07-01"},
        })
    await record_action.handler({
        "title": "Triage discovered opportunities", "kind": "research",
    })
    with Session(engine) as s:
        rows = s.exec(select(Opportunity)).all()
        assert len(rows) == 2
        for r in rows:
            assert r.type == OpportunityType.business
            assert r.source == "discovery"
            assert r.details["opportunity_kind"] == "grant"
        action = s.exec(select(Action)).one()
        assert action.kind == ActionKind.research

    # dedupe: re-saving the same URL updates, never duplicates
    await save_opportunity.handler({
        "type": "business", "title": "Grant a",
        "dedupe_key": "https://grants.example/a", "summary": "updated",
    })
    with Session(engine) as s:
        rows = s.exec(select(Opportunity)).all()
        assert len(rows) == 2
        assert {r.summary for r in rows} == {"updated", "Matches profile: ML platform work."}


async def test_qualify_contract_stage_and_decision(run_ctx):
    await save_opportunity.handler({
        "type": "business", "title": "ML Grant", "dedupe_key": "qualify-1",
    })
    with Session(engine) as s:
        opp_id = s.exec(select(Opportunity)).one().id

    await update_pipeline_status.handler({
        "opportunity_id": opp_id,
        "stage": "analyzing",
        "rationale": "Strong capability fit; deadline feasible.",
    })
    await record_decision.handler({
        "summary": "Qualified ML Grant: analyze further",
        "kind": "choice",
        "opportunity_id": opp_id,
        "rationale": "Fit + value; low competition signal.",
    })
    with Session(engine) as s:
        assert s.get(Opportunity, opp_id).stage == PipelineStage.analyzing
        decisions = s.exec(
            select(Decision).where(Decision.opportunity_id == opp_id)
        ).all()
        # update_pipeline_status may log its own stage_change decision;
        # the contract's choice row must exist with a rationale.
        assert any(
            d.kind == DecisionKind.choice and d.rationale for d in decisions
        )
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_write_back_contracts.py -v`
Expected: 5 PASS immediately (these exercise existing handlers). If either
new test fails, investigate the handler or the contract assumption — report
rather than weakening assertions.

- [ ] **Step 3: Commit**

```bash
git add tests/test_write_back_contracts.py
git commit -m "test(business-pack): write-back contract tests — discover rows/dedupe, qualify stage+decision"
```

---

### Task 5: Endpoint coverage for the business capabilities

**Files:**
- Modify: `tests/test_capabilities_api.py`

- [ ] **Step 1: Append the tests**

In `tests/test_capabilities_api.py`, append:

```python
def _seed_business_opportunity() -> str:
    with Session(engine) as s:
        opp = services.upsert_opportunity(
            s, type=OpportunityType.business, title="ML tooling grant",
            dedupe_key="cap-biz-test", organization="GrantCo", url=None,
            location=None, summary="Grant for ML developer tooling.",
            source="discovery",
            details={"opportunity_kind": "grant", "deadline": "2026-07-01"},
        )
        return opp.id


def test_list_includes_business_capabilities(client):
    names = {c["name"] for c in client.get("/api/capabilities").json()}
    assert {
        "discover-opportunities", "qualify-opportunity",
        "analyze-opportunity", "draft-pursuit",
    } <= names
    assert len(names) == 9


def test_qualify_requires_opportunity_422(client):
    r = client.post("/api/capabilities/qualify-opportunity", json={})
    assert r.status_code == 422


def test_discover_invokes_without_opportunity(client, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        "app.routers.capabilities.stream_run", _fake_stream(captured)
    )
    r = client.post("/api/capabilities/discover-opportunities", json={"input": "grants for ML tooling"})
    assert r.status_code == 200
    assert "business-pack:discover-opportunities" in captured["prompt"]
    assert "grants for ML tooling" in captured["prompt"]
    assert "Candidate profile" in captured["prompt"]  # include_profile


def test_invoke_qualify_templates_business_skill(client, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        "app.routers.capabilities.stream_run", _fake_stream(captured)
    )
    opp_id = _seed_business_opportunity()
    r = client.post(
        "/api/capabilities/qualify-opportunity", json={"opportunity_id": opp_id}
    )
    assert r.status_code == 200
    assert "business-pack:qualify-opportunity" in captured["prompt"]
    assert opp_id in captured["prompt"]
    assert '"opportunity_kind": "grant"' in captured["prompt"]
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_capabilities_api.py -v`
Expected: 12 PASS (8 existing + 4 new) — the registry drives the endpoint, so
these pass without router changes. If any fails, the registry entry (not the
router) is the suspect.

- [ ] **Step 3: Commit**

```bash
git add tests/test_capabilities_api.py
git commit -m "test(api): business capabilities — list, validation, templated prompts"
```

---

### Task 6: Live seam gate (qualify-opportunity)

**Files:**
- Create: `tests/test_business_pack_live.py`

- [ ] **Step 1: Write the gated live test**

Create `tests/test_business_pack_live.py`:

```python
"""Live gate (business pack): a REAL local-CLI agent session must discover
the second repo-local plugin, invoke qualify-opportunity, and follow its
write-back contract (stage change + decision row).

Run: OH_RUN_LIVE_PROBE=1 uv run pytest tests/test_business_pack_live.py -v
Needs an authed local `claude` CLI. Deliberately no web and no OpenAI
dependency: qualification works from the inlined opportunity + profile.
"""

from __future__ import annotations

import os

import pytest
from sqlmodel import Session, select

from app import capabilities as caps
from app import services
from app.agent import runner
from app.db import engine
from app.models import Decision, OpportunityType, PipelineStage, Profile

pytestmark = pytest.mark.skipif(
    os.environ.get("OH_RUN_LIVE_PROBE") != "1",
    reason="live probe: set OH_RUN_LIVE_PROBE=1 (needs authed claude CLI)",
)


async def test_live_qualify_changes_stage_and_records_decision():
    with Session(engine) as s:
        opp = services.upsert_opportunity(
            s, type=OpportunityType.business, title="Fractional ML platform lead",
            dedupe_key="live-qualify-probe", organization="Seed-stage fintech",
            url=None, location="Remote",
            summary=(
                "Fractional engagement: own the PyTorch training platform 2 days/week "
                "for a 12-person fintech; 6-month initial term."
            ),
            source="manual",
            details={"opportunity_kind": "fractional", "value_estimate": "$8k/mo",
                     "deadline": "2026-07-15"},
        )
        services.set_stage(s, opp, PipelineStage.qualifying, rationale="probe seed")
        opp_id = opp.id
        s.add(Profile(
            headline="Staff ML Engineer — training platforms",
            summary="9 years building PyTorch training infrastructure on Kubernetes; led MLOps teams.",
            skills=["pytorch", "kubernetes", "mlops", "python"],
            target_titles=["Staff ML Engineer", "Fractional ML lead"],
            locations=["Remote"],
        ))
        s.commit()

    cap = caps.REGISTRY["qualify-opportunity"]
    with Session(engine) as s:
        opp = services.get_opportunity(s, opp_id)
        profile = s.exec(select(Profile)).first()
        prompt = caps.build_prompt(cap, opportunity=opp, profile=profile)

    events = [e async for e in runner.stream_run(prompt, model=None, api_key=None)]
    assert events[-1]["type"] == "status" and events[-1]["content"] == "completed", (
        f"run did not complete cleanly; last events: {events[-3:]}"
    )

    with Session(engine) as s:
        opp = services.get_opportunity(s, opp_id)
        assert opp.stage != PipelineStage.qualifying, (
            "skill never called update_pipeline_status — seam FAILED"
        )
        assert opp.stage in (
            PipelineStage.analyzing, PipelineStage.active, PipelineStage.lost
        )
        decisions = s.exec(
            select(Decision).where(Decision.opportunity_id == opp_id)
        ).all()
        choice = [d for d in decisions if d.kind.value == "choice"]
        assert choice, "skill never called record_decision — seam FAILED"
        assert choice[-1].rationale, "decision row has empty rationale"
```

- [ ] **Step 2: Verify it skips offline**

Run: `uv run pytest tests/test_business_pack_live.py -v`
Expected: 1 skipped.

- [ ] **Step 3: Run the live gate** (authed `claude` CLI on this machine)

Run: `OH_RUN_LIVE_PROBE=1 uv run pytest tests/test_business_pack_live.py -v -x`
(use a generous timeout, e.g. 420000 ms)
Expected: PASS in ~1-3 minutes. If the run completes but no Skill/tool calls
appear, inspect the persisted `tool_use` events before changing anything —
slice A+D proved plugin-qualified names work, so naming is NOT the first
suspect here; a second-plugin discovery problem would be (check both plugins
appear; try a one-off with only business-pack in `plugins=` to isolate).

- [ ] **Step 4: Commit**

```bash
git add tests/test_business_pack_live.py
git commit -m "test(business-pack): live seam gate — second plugin discovered, qualify contract followed"
```

---

### Task 7: Full verification + docs

- [ ] **Step 1: Full suite**

Run: `uv run pytest -q`
Expected: ~148 passed, 4 skipped (137 prior + 11 net-new offline + 1 new live skip), 0 failures.

- [ ] **Step 2: Frontend build (no changes expected — regression only)**

Run: `cd frontend && npm run build`
Expected: success (buttons for the 4 new capabilities render from the API at
runtime; no code change).

- [ ] **Step 3: Mark the spec implemented**

In `docs/superpowers/specs/2026-06-12-business-pack-design.md`, change
`**Status:** Approved design` to
`**Status:** Implemented (plan docs/superpowers/plans/2026-06-12-business-pack.md); live gate <PASSED/pending> <date>` — reflect the actual Task 6 outcome.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-06-12-business-pack-design.md
git commit -m "docs(spec): mark business-pack spec implemented"
```

Then follow superpowers:finishing-a-development-branch (repo pattern: merge
to main + push after the full suite is green).
