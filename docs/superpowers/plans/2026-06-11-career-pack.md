# Career Pack (Authored-Skill Seam + Capabilities) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Author the career-pack plugin (5 skills) the agent discovers via the Agent SDK, invokable from chat and a templated capability endpoint, whose outputs land as structured rows + provenance-attributed artifacts, with generative artifacts auto-grounded.

**Architecture:** A repo-local SDK plugin at `skills/career-pack/` is passed to `ClaudeAgentOptions.plugins` with an absolute path (per-run session-cwd isolation untouched). `app/capabilities.py` is a registry that maps capability names to plugin-qualified skills and builds deterministic prompts (opportunity block, profile block, pasted input). A new router streams capability runs through the existing `stream_run` SSE machinery. After every run, the runner best-effort auto-grounds generative-kind artifacts created by that run via slice C's `run_grounding_check`.

**Tech Stack:** FastAPI + SQLModel/SQLite, claude-agent-sdk 0.2.93 (local `claude` CLI), Next.js/React/Tailwind frontend, pytest (offline by default, fake `query_fn` / monkeypatched embedders).

**Spec:** `docs/superpowers/specs/2026-06-11-career-pack-design.md`

**Branch:** create `feature/phase2-career-pack` from `main` before Task 1.

**Conventions used throughout** (match existing code):
- Tests are offline: agent faked via `query_fn`, embedders faked via monkeypatching a module-level `_*_embedder` indirection.
- Run the suite with `uv run pytest -q` (or a single file: `uv run pytest tests/<file> -v`).
- The lexical fake embedder used in grounding tests: `[[float(t.lower().count(w)) for w in VOCAB] for t in texts]`.

---

### Task 1: Career-pack plugin (manifest + 5 SKILL.md files) with static validity tests

**Files:**
- Test: `tests/test_career_pack.py`
- Create: `skills/career-pack/.claude-plugin/plugin.json`
- Create: `skills/career-pack/skills/enrich-opportunity/SKILL.md`
- Create: `skills/career-pack/skills/company-research/SKILL.md`
- Create: `skills/career-pack/skills/cv-tailor/SKILL.md`
- Create: `skills/career-pack/skills/interview-prep/SKILL.md`
- Create: `skills/career-pack/skills/fit-analysis/SKILL.md`

- [ ] **Step 1: Write the failing static tests**

Create `tests/test_career_pack.py`:

```python
"""Static validity of the career-pack plugin + the runner seam config.

A renamed/missing skill must fail loudly here — the SDK would otherwise just
discover zero skills and the agent would silently improvise.
"""

from __future__ import annotations

import json
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parent.parent / "skills" / "career-pack"
EXPECTED_SKILLS = {
    "enrich-opportunity",
    "company-research",
    "cv-tailor",
    "interview-prep",
    "fit-analysis",
}


def test_plugin_manifest_parses():
    manifest = json.loads((PACK_DIR / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "career-pack"
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

Run: `uv run pytest tests/test_career_pack.py -v`
Expected: FAIL (FileNotFoundError — `skills/career-pack` does not exist).

- [ ] **Step 3: Create the plugin manifest**

Create `skills/career-pack/.claude-plugin/plugin.json`:

```json
{
  "name": "career-pack",
  "description": "Opportunity Hunter authored career skills: paste-enrichment, company research, CV tailoring, interview prep, fit analysis.",
  "version": "0.1.0"
}
```

- [ ] **Step 4: Create the five SKILL.md files**

Create `skills/career-pack/skills/enrich-opportunity/SKILL.md`:

```markdown
---
name: enrich-opportunity
description: Use when the user pastes a job posting or asks to add a job/opportunity to their pipeline — extracts it into a structured opportunity row plus a follow-up action.
---

# Enrich Opportunity (add-by-paste)

Turn a pasted job posting (or a rough description of one) into a structured
opportunity in the pipeline. Extract only what the text actually says — never
guess salary, location, or seniority that is not stated.

## Steps

1. Read the pasted posting in the prompt's "Input" section.
2. Extract: title, organization, url (if present), location, a 2-3 sentence
   summary, and type-specific details (salary, seniority, employment_type,
   skills — only when stated).
3. Compute `dedupe_key`: the posting URL if present, else
   `<organization>|<title>` lowercased.
4. Call `mcp__app__save_opportunity` (write-back contract below).
5. Call `mcp__app__record_action` for the obvious next step.
6. Reply with a 1-2 sentence confirmation naming the opportunity.

## Write-back contract (MUST)

- `mcp__app__save_opportunity` with: `type="job"` (or `"business"` when it is
  clearly not employment), `title`, `organization`, `url`, `location`,
  `summary`, `source="paste"`, `dedupe_key` (step 3), `details` (only stated
  fields).
- `mcp__app__record_action` with:
  `title="Review & qualify: <organization> — <title>"`, `kind="research"`, and
  the saved opportunity's id as `opportunity_id` (use the id echoed back by
  save_opportunity).

Do NOT save an artifact; this capability produces structured rows only.
```

Create `skills/career-pack/skills/company-research/SKILL.md`:

```markdown
---
name: company-research
description: Use when the user asks to research a company or an opportunity's organization — produces a sourced research-brief artifact linked to the opportunity.
---

# Company Research

Build a concise, sourced research brief on the organization behind an
opportunity. Use web search; cite sources. Facts you could not verify must be
written as `[MISSING: <what you looked for>]` — never invented.

## Steps

1. Identify the organization and role from the prompt's "Opportunity" block.
2. Use `WebSearch` (and `WebFetch` on promising pages) to gather: overview &
   products, size/funding/recent news, tech-stack signals, culture signals,
   and anything bearing on this specific role.
3. Write the brief in markdown with these sections: `## Company overview`,
   `## Products & market`, `## Funding & news`, `## Tech & engineering signals`,
   `## Culture signals`, `## Relevance to this role`, `## Sources` (URLs).
4. Call `mcp__app__save_artifact` (write-back contract below).
5. If you learned concrete fields the opportunity row lacks (canonical url, HQ
   location), also call `mcp__app__save_opportunity` passing the SAME
   `dedupe_key` shown in the Opportunity block, to update it idempotently.
6. Reply with a 3-bullet summary of the most decision-relevant findings.

## Write-back contract (MUST)

- `mcp__app__save_artifact` with: `title="Research brief — <organization>"`,
  `kind="research_brief"`, `opportunity_id` from the Opportunity block,
  `provenance="career-pack:company-research"`, `body` = the full markdown
  brief.
```

Create `skills/career-pack/skills/cv-tailor/SKILL.md`:

```markdown
---
name: cv-tailor
description: Use when the user asks to tailor their CV/resume for an opportunity — produces an ATS-friendly CV artifact grounded in their corpus, never inventing experience.
---

# CV Tailor (ATS, corpus-grounded)

Produce a CV tailored to one opportunity, grounded EXCLUSIVELY in the user's
corpus. This document asserts facts about the user — fabrication is the one
unforgivable failure.

## Grounding rules (non-negotiable)

- Before writing, call `mcp__app__search_corpus` for each major requirement in
  the opportunity (role skills, domain, leadership, tooling) — at least 3
  queries.
- Every experience claim, employer, date, metric, and skill MUST come from a
  corpus passage or the Candidate profile block. If the posting wants
  something you cannot find, write `[MISSING: <the thing>]` in its place
  instead of inventing it.
- Do not inflate titles, dates, or numbers. Reword freely; never add facts.

## ATS rules

- Standard section headings: Summary, Skills, Experience, Education.
- Plain markdown: no tables, no images, no multi-column tricks.
- Mirror the posting's exact keyword spellings where the corpus supports them.

## Steps

1. Read the Opportunity and Candidate profile blocks.
2. Run the corpus searches (grounding rules above).
3. Draft the CV: summary targeted at the role, skills list limited to
   supported skills, reverse-chronological experience with supported bullets.
4. Call `mcp__app__save_artifact` (write-back contract below).
5. Reply with what you emphasized and list any `[MISSING: …]` gaps.

## Write-back contract (MUST)

- `mcp__app__save_artifact` with: `title="CV — <organization> <role title>"`,
  `kind="cv"`, `opportunity_id` from the Opportunity block,
  `provenance="career-pack:cv-tailor"`, `body` = the full markdown CV.

The backend automatically runs a grounding check on this artifact; it lands in
review as `needs_review`. That is expected — do not try to approve it.
```

Create `skills/career-pack/skills/interview-prep/SKILL.md`:

```markdown
---
name: interview-prep
description: Use when the user asks to prepare for an interview for an opportunity — produces a prep document with corpus-grounded STAR stories plus prep actions.
---

# Interview Prep

Build a focused prep doc for one opportunity's interviews. Stories must come
from the user's real experience (corpus / profile) — mark gaps
`[MISSING: <the thing>]` rather than inventing anecdotes.

## Steps

1. Read the Opportunity and Candidate profile blocks.
2. Call `mcp__app__search_corpus` for experiences matching the role's likely
   themes (leadership, hard technical problems, the posting's domain).
3. Write the doc with sections: `## Role & company angle`,
   `## Likely technical questions`, `## Likely behavioral questions`,
   `## STAR stories` (each grounded in a corpus passage),
   `## Questions to ask them`, `## Logistics & gaps`.
4. Call `mcp__app__save_artifact` (write-back contract below).
5. Call `mcp__app__record_action` for concrete prep tasks (one per gap or
   rehearsal item, max 3), `kind="prep"`, linked to the opportunity.
6. Reply with the top 3 things to rehearse.

## Write-back contract (MUST)

- `mcp__app__save_artifact` with:
  `title="Interview prep — <organization> <role title>"`, `kind="other"`,
  `opportunity_id` from the Opportunity block,
  `provenance="career-pack:interview-prep"`, `body` = the full markdown doc.
- `mcp__app__record_action` as in step 5.
```

Create `skills/career-pack/skills/fit-analysis/SKILL.md`:

```markdown
---
name: fit-analysis
description: Use when the user asks how well an opportunity fits them, or to score/compare an opportunity — produces a scored fit-analysis artifact and a decision row. Re-runnable.
---

# Fit Analysis

Score how well one opportunity fits the candidate. Be honest and
decision-useful: the user triages their pipeline with these scores, so an
inflated score is worse than a low one. Re-running on the same opportunity is
expected — each run saves a new artifact version and a new decision row.

## Steps

1. Read the Opportunity and Candidate profile blocks. If the profile block is
   empty, call `mcp__app__search_corpus` for the role's main requirements.
2. Score each dimension 1-5 with one sentence of evidence: skills match,
   seniority match, domain match, location/logistics, growth potential.
3. Compute overall = mean of the dimensions, one decimal.
4. Write the analysis in markdown: a score table, `## Strengths`,
   `## Gaps & risks`, `## Verdict` (pursue / deprioritize / pass — and why).
5. Call `mcp__app__save_artifact` then `mcp__app__record_decision`
   (write-back contract below).
6. Reply with the overall score and the verdict sentence.

## Write-back contract (MUST)

- `mcp__app__save_artifact` with:
  `title="Fit analysis — <organization> <role title>"`, `kind="fit_analysis"`,
  `opportunity_id` from the Opportunity block,
  `provenance="career-pack:fit-analysis"`, `body` = the full markdown
  analysis.
- `mcp__app__record_decision` with:
  `summary="Fit <overall>/5 — <verdict word>: <role title> @ <organization>"`,
  `kind="choice"`, `opportunity_id`, `rationale` = the 2-3 decisive reasons.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_career_pack.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add skills/ tests/test_career_pack.py
git commit -m "feat(skills): career-pack plugin — 5 authored skills with write-back contracts"
```

---

### Task 2: Capability registry (`app/capabilities.py`)

**Files:**
- Test: `tests/test_capabilities.py`
- Create: `app/capabilities.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_capabilities.py`:

```python
from __future__ import annotations

from pathlib import Path

from app import capabilities as caps
from app.models import Opportunity, OpportunityType, Profile

PACK_SKILLS_DIR = (
    Path(__file__).resolve().parent.parent / "skills" / "career-pack" / "skills"
)


def test_registry_has_the_five_capabilities():
    assert set(caps.REGISTRY) == {
        "enrich-opportunity",
        "company-research",
        "cv-tailor",
        "interview-prep",
        "fit-analysis",
    }


def test_registry_skills_match_pack_directories():
    dirs = {p.name for p in PACK_SKILLS_DIR.iterdir() if p.is_dir()}
    assert {c.skill for c in caps.CAPABILITIES} == dirs


def test_skill_names_are_plugin_qualified():
    assert len(caps.SKILL_NAMES) == 5
    assert "career-pack:fit-analysis" in caps.SKILL_NAMES


def test_build_prompt_includes_opportunity_and_profile():
    cap = caps.REGISTRY["fit-analysis"]
    opp = Opportunity(
        type=OpportunityType.job, title="Staff ML Engineer",
        organization="Acme AI", summary="PyTorch platform team",
        dedupe_key="acme|staff-ml",
    )
    profile = Profile(headline="Staff ML engineer", skills=["pytorch", "k8s"])
    prompt = caps.build_prompt(cap, opportunity=opp, profile=profile)
    assert 'career-pack:fit-analysis' in prompt
    assert f"- id: {opp.id}" in prompt
    assert "Staff ML Engineer" in prompt and "Acme AI" in prompt
    assert "- dedupe_key: acme|staff-ml" in prompt
    assert "pytorch" in prompt


def test_build_prompt_profile_placeholder_when_missing():
    cap = caps.REGISTRY["cv-tailor"]
    opp = Opportunity(type=OpportunityType.job, title="Engineer")
    prompt = caps.build_prompt(cap, opportunity=opp, profile=None)
    assert "(no synthesized profile" in prompt


def test_build_prompt_enrich_carries_input_only():
    cap = caps.REGISTRY["enrich-opportunity"]
    prompt = caps.build_prompt(cap, input_text="We are hiring a Platform Engineer…")
    assert "Platform Engineer" in prompt
    assert "Opportunity:" not in prompt
    assert "Candidate profile" not in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_capabilities.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.capabilities'`)

- [ ] **Step 3: Implement the registry**

Create `app/capabilities.py`:

```python
"""Capability registry — named, templated invocations of career-pack skills.

A capability wraps ONE authored skill in a deterministic prompt: the UI (or
any client) POSTs /api/capabilities/{name} and the backend builds the exact
prompt naming the plugin-qualified skill, so invocation never depends on
free-form chat phrasing. Free-form chat can still trigger the same skills
naturally — the registry is the reliable path, not the only one.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import Opportunity, Profile

PLUGIN_NAME = "career-pack"


@dataclass(frozen=True)
class Capability:
    name: str  # URL slug / UI identity (same as the skill directory name)
    skill: str  # SKILL.md `name` inside the plugin
    label: str
    description: str
    requires_opportunity: bool
    requires_input: bool
    include_profile: bool  # inline the synthesized Profile row into the prompt


CAPABILITIES = [
    Capability(
        name="enrich-opportunity",
        skill="enrich-opportunity",
        label="Add by paste",
        description="Paste a job posting; extract it into a pipeline opportunity.",
        requires_opportunity=False,
        requires_input=True,
        include_profile=False,
    ),
    Capability(
        name="company-research",
        skill="company-research",
        label="Company research",
        description="Research the company behind an opportunity into a sourced brief.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=False,
    ),
    Capability(
        name="cv-tailor",
        skill="cv-tailor",
        label="Tailor CV",
        description="Corpus-grounded, ATS-friendly CV for an opportunity.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=True,
    ),
    Capability(
        name="interview-prep",
        skill="interview-prep",
        label="Interview prep",
        description="Prep doc with grounded STAR stories and questions to ask.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=True,
    ),
    Capability(
        name="fit-analysis",
        skill="fit-analysis",
        label="Fit analysis",
        description="Re-runnable scored fit analysis of your profile vs the opportunity.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=True,
    ),
]

REGISTRY: dict[str, Capability] = {c.name: c for c in CAPABILITIES}

# Plugin-qualified names for ClaudeAgentOptions.skills.
SKILL_NAMES = [f"{PLUGIN_NAME}:{c.skill}" for c in CAPABILITIES]


def opportunity_block(opp: Opportunity) -> str:
    lines = [f"- id: {opp.id}", f"- title: {opp.title}"]
    if opp.organization:
        lines.append(f"- organization: {opp.organization}")
    if opp.url:
        lines.append(f"- url: {opp.url}")
    if opp.location:
        lines.append(f"- location: {opp.location}")
    if opp.summary:
        lines.append(f"- summary: {opp.summary}")
    if opp.dedupe_key:
        lines.append(f"- dedupe_key: {opp.dedupe_key}")
    if opp.details:
        lines.append(f"- details: {opp.details}")
    return "\n".join(lines)


def profile_block(profile: Profile | None) -> str:
    if profile is None:
        return "- (no synthesized profile — use mcp__app__search_corpus instead)"
    lines = []
    if profile.headline:
        lines.append(f"- headline: {profile.headline}")
    if profile.summary:
        lines.append(f"- summary: {profile.summary}")
    if profile.skills:
        lines.append(f"- skills: {', '.join(profile.skills)}")
    if profile.target_titles:
        lines.append(f"- target titles: {', '.join(profile.target_titles)}")
    if profile.locations:
        lines.append(f"- locations: {', '.join(profile.locations)}")
    return "\n".join(lines) or "- (empty profile)"


def build_prompt(
    cap: Capability,
    *,
    opportunity: Opportunity | None = None,
    input_text: str = "",
    profile: Profile | None = None,
) -> str:
    parts = [
        f'Use the "{PLUGIN_NAME}:{cap.skill}" skill now (via the Skill tool), '
        "then follow its write-back contract exactly."
    ]
    if opportunity is not None:
        parts.append("Opportunity:\n" + opportunity_block(opportunity))
    if cap.include_profile:
        parts.append("Candidate profile (synthesized):\n" + profile_block(profile))
    if input_text.strip():
        parts.append("Input:\n" + input_text.strip())
    return "\n\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_capabilities.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add app/capabilities.py tests/test_capabilities.py
git commit -m "feat(capabilities): registry + deterministic prompt templating for career-pack skills"
```

---

### Task 3: Runner seam — plugin discovery, skills, expanded allowlist

**Files:**
- Test: `tests/test_career_pack.py` (append)
- Modify: `tests/test_agent.py` (gate test: `WebFetch` is no longer forbidden)
- Modify: `app/config.py`
- Modify: `app/agent/runner.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_career_pack.py`:

```python
from app import capabilities as caps  # noqa: E402
from app.agent import runner  # noqa: E402
from app.agent.tools import ALL_TOOL_NAMES  # noqa: E402
from app.config import get_config  # noqa: E402


def test_build_options_enables_career_pack(tmp_path):
    opts = runner.build_options(model=None, cwd=tmp_path, api_key=None)
    cfg = get_config()
    assert cfg.career_pack_dir.is_absolute()
    assert opts.plugins == [{"type": "local", "path": str(cfg.career_pack_dir)}]
    assert opts.skills == caps.SKILL_NAMES
    for name in ("Skill", "Read", "WebSearch", "WebFetch"):
        assert name in opts.allowed_tools
    assert all(t in opts.allowed_tools for t in ALL_TOOL_NAMES)
    # the plugin path must point at the real pack (not depend on cwd)
    assert (cfg.career_pack_dir / ".claude-plugin" / "plugin.json").exists()


async def test_gate_allows_skill_tools_denies_others():
    for allowed in ("Skill", "Read", "WebSearch", "WebFetch"):
        assert (await runner._gate(allowed, {}, None)).behavior == "allow"
    for forbidden in ("Bash", "Write", "Edit", "mcp__app__delete_everything"):
        assert (await runner._gate(forbidden, {}, None)).behavior == "deny"
```

In `tests/test_agent.py`, the existing gate test forbids `WebFetch`, which this
task legitimately allows. Change:

```python
    for forbidden in ("Bash", "Write", "WebFetch", "mcp__app__delete_everything"):
```

to:

```python
    for forbidden in ("Bash", "Write", "Edit", "mcp__app__delete_everything"):
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_career_pack.py tests/test_agent.py -v`
Expected: the two new tests FAIL (`AppConfig` has no `career_pack_dir`; gate denies `Skill`); existing tests PASS.

- [ ] **Step 3: Add config field**

In `app/config.py`, after the `sessions_dir` line (`sessions_dir: Path = ROOT_DIR / "sessions"  # per-agent-session working dirs`), add:

```python
    # Authored-skill plugin (career pack). Absolute path — the agent session's
    # cwd is an isolated per-run dir, so discovery must NOT be cwd-relative.
    career_pack_dir: Path = ROOT_DIR / "skills" / "career-pack"
```

- [ ] **Step 4: Wire the runner**

In `app/agent/runner.py`:

1. Add import (after the `from app.agent.tools import (...)` block):

```python
from app.capabilities import SKILL_NAMES
```

2. Replace the `ALLOWED_TOOLS` assignment and its comment:

```python
# The agent may call our in-process write-back tools, the Skill tool (career
# pack), Read (skills' supporting files), and web research tools. The gate
# below denies everything else (ToolSearch, a benign discovery meta-tool, is
# exempt by the SDK and is what lets the agent find these mcp__app__* tools).
ALLOWED_TOOLS = [*ALL_TOOL_NAMES, "Skill", "Read", "WebSearch", "WebFetch"]
```

3. In `build_options`, replace the `setting_sources=None,` line (keeping it) and add the two new options so the return ends:

```python
        cwd=str(cwd),
        env=env,
        # Authored skills ship as a repo-local plugin with an ABSOLUTE path —
        # per-run cwd isolation stays intact and discovery can't silently
        # find zero skills. `skills=` is the SDK's single enablement knob
        # (auto-configures the Skill tool); setting_sources stays None.
        plugins=[{"type": "local", "path": str(cfg.career_pack_dir)}],
        skills=list(SKILL_NAMES),
        setting_sources=None,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_career_pack.py tests/test_agent.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add app/config.py app/agent/runner.py tests/test_career_pack.py tests/test_agent.py
git commit -m "feat(runner): discover career-pack plugin via absolute path; allow Skill/Read/Web tools"
```

---

### Task 4: Auto-grounding service function

**Files:**
- Test: `tests/test_auto_grounding.py`
- Modify: `app/grounding_service.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_auto_grounding.py`:

```python
"""Post-run auto-grounding: generative artifacts from a run get checked and
land needs_review; everything else (and every failure mode) stays draft."""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app import grounding_service, services
from app.agent import runner
from app.corpus_service import ingest_document
from app.db import engine
from app.models import (
    Artifact,
    ArtifactKind,
    DocumentMediaType,
    DocumentSource,
    GroundingReport,
    ReviewStatus,
)

_VOCAB = ["python", "kubernetes", "leadership", "apis"]


def _lexical_embedder(texts):
    return [[float(t.lower().count(w)) for w in _VOCAB] for t in texts]


@pytest.fixture
def fake_auto_embedder(monkeypatch):
    monkeypatch.setattr(
        "app.grounding_service._auto_embedder", lambda session: _lexical_embedder
    )


def _seed_corpus():
    with Session(engine) as s:
        ingest_document(
            s, title="resume.md", source_kind=DocumentSource.paste,
            media_type=DocumentMediaType.md,
            data=b"I build python apis and run kubernetes clusters with leadership.",
            embedder=_lexical_embedder,
        )


def _make_artifact(kind: ArtifactKind, run_id: str | None) -> int:
    with Session(engine) as s:
        a = services.add_artifact(
            s, title="t",
            body="I build python apis daily. I won a Nobel prize in chemistry.",
            kind=kind, run_id=run_id,
        )
        return a.id


def test_generative_artifact_gets_checked(fake_auto_embedder):
    _seed_corpus()
    run = runner.create_run("x", model=None)
    aid = _make_artifact(ArtifactKind.cv, run.id)
    assert grounding_service.auto_ground_run_artifacts(run.id) == [aid]
    with Session(engine) as s:
        assert s.get(Artifact, aid).review_status == ReviewStatus.needs_review
        report = s.exec(
            select(GroundingReport).where(GroundingReport.artifact_id == aid)
        ).one()
        assert report.unsupported_count >= 1  # the Nobel prize sentence


def test_non_generative_kinds_stay_draft(fake_auto_embedder):
    _seed_corpus()
    run = runner.create_run("x", model=None)
    aid = _make_artifact(ArtifactKind.research_brief, run.id)
    assert grounding_service.auto_ground_run_artifacts(run.id) == []
    with Session(engine) as s:
        assert s.get(Artifact, aid).review_status == ReviewStatus.draft


def test_failure_is_non_fatal(fake_auto_embedder):
    # empty corpus -> check_grounding raises ValueError -> skipped, stays draft
    run = runner.create_run("x", model=None)
    aid = _make_artifact(ArtifactKind.cv, run.id)
    assert grounding_service.auto_ground_run_artifacts(run.id) == []
    with Session(engine) as s:
        assert s.get(Artifact, aid).review_status == ReviewStatus.draft
        assert s.exec(
            select(GroundingReport).where(GroundingReport.artifact_id == aid)
        ).first() is None


def test_other_runs_artifacts_untouched(fake_auto_embedder):
    _seed_corpus()
    run_a = runner.create_run("a", model=None)
    run_b = runner.create_run("b", model=None)
    aid_b = _make_artifact(ArtifactKind.cv, run_b.id)
    assert grounding_service.auto_ground_run_artifacts(run_a.id) == []
    with Session(engine) as s:
        assert s.get(Artifact, aid_b).review_status == ReviewStatus.draft
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_auto_grounding.py -v`
Expected: FAIL (`AttributeError: module 'app.grounding_service' has no attribute '_auto_embedder'`)

- [ ] **Step 3: Implement**

In `app/grounding_service.py`:

1. Add `import logging` to the stdlib imports; change the corpus import line
   `from app.corpus_service import Embedder` to
   `from app.corpus_service import Embedder, default_embedder`; add
   `from app.db import engine` after the corpus import; add `ArtifactKind` to
   the `from app.models import (...)` block.

2. Append at the end of the file:

```python
# --------------------------------------------------------------------------- #
# Slice A+D: post-run auto-grounding of generative artifacts.
# --------------------------------------------------------------------------- #

logger = logging.getLogger(__name__)

# Kinds that assert facts about the user — auto-checked after every run.
# Research briefs / fit analyses are about the opportunity, not the corpus,
# so checking them would only produce noise (spec decision).
GENERATIVE_KINDS = (
    ArtifactKind.cv,
    ArtifactKind.cover_letter,
    ArtifactKind.pitch,
    ArtifactKind.outreach,
)


def _auto_embedder(session: Session) -> Embedder:
    """Indirection point: tests monkeypatch this to inject a fake embedder."""
    return default_embedder(session)


def auto_ground_run_artifacts(run_id: str) -> list[int]:
    """Best-effort grounding for generative artifacts created by a run.

    Failures (no OpenAI key, empty corpus) are logged and skipped — the run
    must still succeed; an unchecked artifact simply stays `draft`. Returns
    the artifact ids that were checked.
    """
    with Session(engine) as session:
        ids = list(
            session.exec(
                select(Artifact.id)
                .where(Artifact.run_id == run_id)
                .where(Artifact.kind.in_(GENERATIVE_KINDS))
                .order_by(Artifact.id)
            ).all()
        )
    checked: list[int] = []
    for artifact_id in ids:
        try:
            with Session(engine) as session:
                run_grounding_check(
                    session, artifact_id, embedder=_auto_embedder(session)
                )
            checked.append(artifact_id)
        except Exception as exc:  # noqa: BLE001 — never fail the run
            logger.warning("auto-grounding skipped for artifact %s: %s", artifact_id, exc)
    return checked
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_auto_grounding.py tests/test_grounding_check.py tests/test_grounding_api.py tests/test_grounding_lifecycle.py -v`
Expected: all PASS (existing grounding tests unaffected)

- [ ] **Step 5: Commit**

```bash
git add app/grounding_service.py tests/test_auto_grounding.py
git commit -m "feat(grounding): auto_ground_run_artifacts — best-effort post-run check of generative kinds"
```

---

### Task 5: Runner hook — auto-ground after every successful run

**Files:**
- Test: `tests/test_auto_grounding.py` (append)
- Modify: `app/agent/runner.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_auto_grounding.py`:

```python
from claude_agent_sdk import ResultMessage  # noqa: E402


def _fake_agent():
    async def fake(*, prompt, options):  # noqa: ARG001
        yield ResultMessage(
            subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
            num_turns=1, session_id="sess", result="ok", total_cost_usd=0.0,
        )

    return fake


async def test_stream_run_auto_grounds_on_completion(fake_auto_embedder):
    _seed_corpus()
    run = runner.create_run("tailor my cv", model=None)
    # Simulates the artifact a skill saved mid-run (attributed via run_id).
    aid = _make_artifact(ArtifactKind.cv, run.id)
    events = [
        e async for e in runner.stream_run("tailor my cv", run=run, query_fn=_fake_agent())
    ]
    assert events[-1]["type"] == "status"
    assert events[-1]["content"] == "completed"
    with Session(engine) as s:
        assert s.get(Artifact, aid).review_status == ReviewStatus.needs_review
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auto_grounding.py::test_stream_run_auto_grounds_on_completion -v`
Expected: FAIL (`review_status` is still `draft` — runner never calls the checker)

- [ ] **Step 3: Implement the hook**

In `app/agent/runner.py`:

1. Add `import asyncio` to the stdlib imports (next to `import json`).
2. Add `from app import grounding_service` after the `from app.agent.tools import (...)` block.
3. In `stream_run`, between the end of the `async for` loop and
   `_set_run_status(run_id, RunStatus.completed)`, insert:

```python
        # Review gate: auto-check generative artifacts created by this run
        # (best-effort; never fails the run). to_thread because the embedder
        # is a blocking network call. Applies to chat AND capability runs so
        # the gate can't be bypassed by phrasing.
        await asyncio.to_thread(grounding_service.auto_ground_run_artifacts, run_id)
        _set_run_status(run_id, RunStatus.completed)
```

(No new event is emitted — the frontend already refreshes the canvas on the
`result` event, which picks up the new review status.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_auto_grounding.py tests/test_agent.py -v`
Expected: all PASS (the existing `test_stream_run_persists_streams_and_replays` event-order assertion is untouched because no event is emitted)

- [ ] **Step 5: Commit**

```bash
git add app/agent/runner.py tests/test_auto_grounding.py
git commit -m "feat(runner): auto-ground generative artifacts after every successful run"
```

---

### Task 6: Write-back contract tests (the Phase 2 gate)

Each SKILL.md mandates specific tool calls. The tools execute in-process, so
the gate is testable offline: call each handler with exactly the
contract-shaped args a compliant skill would send and assert the rows AND
their field values (master plan: *"a skill can produce a perfect document and
silently never call the write-back tool"*). The live gate (Task 10) proves a
real agent sends these args; this task proves the args produce correct rows.

**Files:**
- Test: `tests/test_write_back_contracts.py`

- [ ] **Step 1: Write the tests**

Create `tests/test_write_back_contracts.py`:

```python
"""Contract-shaped tool calls -> correct rows with correct field values."""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.agent import runner
from app.agent.tools import (
    current_run_id,
    record_action,
    record_decision,
    save_artifact,
    save_opportunity,
)
from app.db import engine
from app.models import (
    Action,
    ActionKind,
    Artifact,
    ArtifactKind,
    Decision,
    DecisionKind,
    Opportunity,
    ReviewStatus,
)


@pytest.fixture
def run_ctx():
    run = runner.create_run("contract test", model=None)
    token = current_run_id.set(run.id)
    yield run
    current_run_id.reset(token)


async def test_enrich_opportunity_contract(run_ctx):
    result = await save_opportunity.handler({
        "type": "job",
        "title": "Platform Engineer",
        "organization": "Globex",
        "url": "https://globex.example/jobs/42",
        "location": "Berlin",
        "summary": "Platform team, K8s.",
        "source": "paste",
        "dedupe_key": "https://globex.example/jobs/42",
        "details": {"seniority": "senior"},
    })
    assert "Saved opportunity" in result["content"][0]["text"]
    with Session(engine) as s:
        opp = s.exec(
            select(Opportunity).where(
                Opportunity.dedupe_key == "https://globex.example/jobs/42"
            )
        ).one()
        assert opp.title == "Platform Engineer"
        assert opp.organization == "Globex"
        assert opp.location == "Berlin"
        assert opp.source == "paste"
        assert opp.details == {"seniority": "senior"}
        opp_id = opp.id

    await record_action.handler({
        "title": "Review & qualify: Globex — Platform Engineer",
        "kind": "research",
        "opportunity_id": opp_id,
    })
    with Session(engine) as s:
        action = s.exec(select(Action).where(Action.opportunity_id == opp_id)).one()
        assert action.kind == ActionKind.research
        assert action.title.startswith("Review & qualify")

    # contract dedupe: re-saving the same dedupe_key updates, never duplicates
    await save_opportunity.handler({
        "type": "job", "title": "Platform Engineer",
        "dedupe_key": "https://globex.example/jobs/42", "summary": "updated",
    })
    with Session(engine) as s:
        rows = s.exec(select(Opportunity)).all()
        assert len(rows) == 1
        assert rows[0].summary == "updated"


async def test_cv_tailor_contract_artifact_and_versioning(run_ctx):
    await save_opportunity.handler({"type": "job", "title": "Role", "dedupe_key": "k1"})
    with Session(engine) as s:
        opp_id = s.exec(select(Opportunity)).one().id

    args = {
        "title": "CV — Acme AI Staff ML Engineer",
        "body": "## Summary\nExperienced engineer. [MISSING: Rust experience]",
        "opportunity_id": opp_id,
        "kind": "cv",
        "provenance": "career-pack:cv-tailor",
    }
    await save_artifact.handler(args)
    await save_artifact.handler(args)  # re-run -> new version
    with Session(engine) as s:
        arts = s.exec(
            select(Artifact).where(Artifact.opportunity_id == opp_id).order_by(Artifact.version)
        ).all()
        assert [a.version for a in arts] == [1, 2]
        for a in arts:
            assert a.kind == ArtifactKind.cv
            assert a.provenance == "career-pack:cv-tailor"
            assert a.run_id == run_ctx.id  # attributed to the running session
            assert a.review_status == ReviewStatus.draft  # gate runs post-run, not here
            assert "[MISSING:" in a.body  # gaps marked, not fabricated


async def test_fit_analysis_contract_artifact_plus_decision(run_ctx):
    await save_opportunity.handler({"type": "job", "title": "Role", "dedupe_key": "k2"})
    with Session(engine) as s:
        opp_id = s.exec(select(Opportunity)).one().id

    await save_artifact.handler({
        "title": "Fit analysis — Acme AI Staff ML Engineer",
        "body": "| dim | score |\n|---|---|\n| skills | 4 |\n\n## Verdict\nPursue.",
        "opportunity_id": opp_id,
        "kind": "fit_analysis",
        "provenance": "career-pack:fit-analysis",
    })
    await record_decision.handler({
        "summary": "Fit 4.2/5 — pursue: Staff ML Engineer @ Acme AI",
        "kind": "choice",
        "opportunity_id": opp_id,
        "rationale": "Strong skills overlap; seniority match.",
    })
    with Session(engine) as s:
        art = s.exec(select(Artifact).where(Artifact.opportunity_id == opp_id)).one()
        assert art.kind == ArtifactKind.fit_analysis
        assert art.provenance == "career-pack:fit-analysis"
        decision = s.exec(select(Decision).where(Decision.opportunity_id == opp_id)).one()
        assert decision.kind == DecisionKind.choice
        assert decision.summary.startswith("Fit 4.2/5")
        assert decision.rationale
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_write_back_contracts.py -v`
Expected: 3 PASS — these exercise existing handlers (Tasks 1–5 added no new
tool code), so they should pass immediately; if any fails, the handler or a
contract assumption is wrong — fix the code or the SKILL.md contract, not the
test's intent.

- [ ] **Step 3: Commit**

```bash
git add tests/test_write_back_contracts.py
git commit -m "test(career-pack): write-back contract tests — rows and field values per skill contract"
```

---

### Task 7: Capabilities router + app wiring

**Files:**
- Test: `tests/test_capabilities_api.py`
- Create: `app/routers/capabilities.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_capabilities_api.py`:

```python
from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import OpportunityType


def _seed_opportunity() -> str:
    with Session(engine) as s:
        opp = services.upsert_opportunity(
            s, type=OpportunityType.job, title="Staff ML Engineer",
            dedupe_key="cap-test", organization="Acme AI", url=None,
            location=None, summary="PyTorch platform team", source="manual",
            details={},
        )
        return opp.id


def _fake_stream(captured: dict):
    async def fake_stream_run(prompt, *, model=None, api_key=None):  # noqa: ARG001
        captured["prompt"] = prompt
        yield {"run_id": "r1", "seq": 0, "type": "status", "content": "running"}
        yield {"run_id": "r1", "seq": 1, "type": "result", "content": "{}"}

    return fake_stream_run


def test_list_capabilities(client):
    r = client.get("/api/capabilities")
    assert r.status_code == 200
    by_name = {c["name"]: c for c in r.json()}
    assert set(by_name) == {
        "enrich-opportunity", "company-research", "cv-tailor",
        "interview-prep", "fit-analysis",
    }
    assert by_name["fit-analysis"]["requires_opportunity"] is True
    assert by_name["enrich-opportunity"]["requires_input"] is True


def test_invoke_unknown_capability_404(client):
    assert client.post("/api/capabilities/nope", json={}).status_code == 404


def test_invoke_missing_opportunity_id_422(client):
    assert client.post("/api/capabilities/fit-analysis", json={}).status_code == 422


def test_invoke_unknown_opportunity_404(client):
    r = client.post(
        "/api/capabilities/fit-analysis", json={"opportunity_id": "missing"}
    )
    assert r.status_code == 404


def test_invoke_missing_required_input_422(client):
    assert client.post("/api/capabilities/enrich-opportunity", json={}).status_code == 422


def test_invoke_streams_templated_prompt(client, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        "app.routers.capabilities.stream_run", _fake_stream(captured)
    )
    opp_id = _seed_opportunity()
    r = client.post("/api/capabilities/fit-analysis", json={"opportunity_id": opp_id})
    assert r.status_code == 200
    assert "career-pack:fit-analysis" in captured["prompt"]
    assert "Acme AI" in captured["prompt"]
    assert opp_id in captured["prompt"]
    # SSE frames made it to the body
    assert '"type": "status"' in r.text
    assert '"type": "result"' in r.text


def test_invoke_enrich_passes_input(client, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        "app.routers.capabilities.stream_run", _fake_stream(captured)
    )
    r = client.post(
        "/api/capabilities/enrich-opportunity",
        json={"input": "We are hiring a Platform Engineer in Berlin."},
    )
    assert r.status_code == 200
    assert "Platform Engineer" in captured["prompt"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_capabilities_api.py -v`
Expected: FAIL (404s everywhere — router does not exist)

- [ ] **Step 3: Implement the router**

Create `app/routers/capabilities.py`:

```python
"""Capability endpoints — templated invocations of career-pack skills.

POST /api/capabilities/{name} builds the deterministic prompt from the
registry (app.capabilities) and streams an ordinary agent run as SSE — the
same machinery as /api/chat, so events persist and re-attach works.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app import capabilities as caps
from app import settings_service as ss
from app.agent.runner import stream_run
from app.db import get_session
from app.models import Opportunity, Profile

router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])


class CapabilityOut(BaseModel):
    name: str
    label: str
    description: str
    requires_opportunity: bool
    requires_input: bool


class InvokeRequest(BaseModel):
    opportunity_id: str | None = None
    input: str = ""


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@router.get("", response_model=list[CapabilityOut])
def list_capabilities() -> list[CapabilityOut]:
    return [
        CapabilityOut(
            name=c.name, label=c.label, description=c.description,
            requires_opportunity=c.requires_opportunity,
            requires_input=c.requires_input,
        )
        for c in caps.CAPABILITIES
    ]


@router.post("/{name}")
async def invoke(
    name: str, body: InvokeRequest, session: Session = Depends(get_session)
) -> StreamingResponse:
    cap = caps.REGISTRY.get(name)
    if cap is None:
        raise HTTPException(status_code=404, detail=f"unknown capability '{name}'")
    if cap.requires_input and not body.input.strip():
        raise HTTPException(
            status_code=422, detail=f"capability '{name}' requires input"
        )
    opportunity: Opportunity | None = None
    if cap.requires_opportunity:
        if not body.opportunity_id:
            raise HTTPException(
                status_code=422, detail=f"capability '{name}' requires opportunity_id"
            )
        opportunity = session.get(Opportunity, body.opportunity_id)
        if opportunity is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
    profile = (
        session.exec(select(Profile)).first() if cap.include_profile else None
    )
    prompt = caps.build_prompt(
        cap, opportunity=opportunity, input_text=body.input, profile=profile
    )
    model = ss.resolve_agent_model(session)
    api_key = ss.resolve_anthropic_key(session)

    async def gen() -> AsyncIterator[str]:
        async for event in stream_run(prompt, model=model, api_key=api_key):
            yield _sse(event)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

In `app/main.py`, add `capabilities,` to the `from app.routers import (...)`
list (alphabetical — after `attention,`) and register it after the chat router:

```python
app.include_router(chat.router)
app.include_router(capabilities.router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_capabilities_api.py -v`
Expected: 8 PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/capabilities.py app/main.py tests/test_capabilities_api.py
git commit -m "feat(api): /api/capabilities — list + templated SSE invoke of career-pack skills"
```

---

### Task 8: Frontend API client

**Files:**
- Modify: `frontend/lib/api.ts` (full replacement below)

- [ ] **Step 1: Replace `frontend/lib/api.ts`**

```typescript
// Minimal API client. In dev, /api is proxied to FastAPI (:8000) via Next
// rewrites; in prod the app is served by FastAPI on the same origin.

export type AgentEvent = {
  run_id: string;
  seq: number;
  type: "status" | "token" | "tool_use" | "tool_result" | "result" | "error";
  content: string;
};

export type Note = {
  id: number;
  title: string;
  body: string;
  run_id: string | null;
  created_at: string;
};

export type Artifact = {
  id: number;
  title: string;
  body: string;
  kind: string;
  opportunity_id: string | null;
  provenance: string | null;
  version: number;
  review_status: "draft" | "needs_review" | "approved";
  created_at: string;
};

export type Opportunity = {
  id: string;
  title: string;
  organization: string | null;
  stage: string;
};

export type Capability = {
  name: string;
  label: string;
  description: string;
  requires_opportunity: boolean;
  requires_input: boolean;
};

export type SettingsView = {
  anthropic_key_configured: boolean;
  openai_key_configured: boolean;
  agent_model: string;
  default_agent_model: string;
  deep_analysis_model: string;
};

/** POST JSON to an SSE endpoint and dispatch each agent event. */
async function streamSSE(
  url: string,
  body: unknown,
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`${url} failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx: number;
    // SSE frames are separated by a blank line.
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of frame.split("\n")) {
        if (line.startsWith("data:")) {
          const json = line.slice(5).trim();
          if (json) onEvent(JSON.parse(json) as AgentEvent);
        }
      }
    }
  }
}

/** POST a prompt and stream agent events. */
export async function streamChat(
  prompt: string,
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSSE("/api/chat", { prompt }, onEvent, signal);
}

/** Invoke a named capability (templated skill run) and stream its events. */
export async function invokeCapability(
  name: string,
  body: { opportunity_id?: string; input?: string },
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSSE(
    `/api/capabilities/${encodeURIComponent(name)}`,
    body,
    onEvent,
    signal,
  );
}

export async function fetchCapabilities(): Promise<Capability[]> {
  const res = await fetch("/api/capabilities");
  if (!res.ok) throw new Error(`capabilities failed: ${res.status}`);
  return res.json();
}

export async function fetchOpportunities(): Promise<Opportunity[]> {
  const res = await fetch("/api/opportunities");
  if (!res.ok) throw new Error(`opportunities failed: ${res.status}`);
  return res.json();
}

export async function fetchArtifacts(): Promise<Artifact[]> {
  const res = await fetch("/api/artifacts");
  if (!res.ok) throw new Error(`artifacts failed: ${res.status}`);
  return res.json();
}

export async function fetchNotes(runId?: string): Promise<Note[]> {
  const url = runId ? `/api/notes?run_id=${encodeURIComponent(runId)}` : "/api/notes";
  const res = await fetch(url);
  if (!res.ok) throw new Error(`notes failed: ${res.status}`);
  return res.json();
}

export async function getSettings(): Promise<SettingsView> {
  const res = await fetch("/api/settings");
  if (!res.ok) throw new Error(`settings failed: ${res.status}`);
  return res.json();
}

export async function updateSettings(
  body: Partial<{ anthropic_api_key: string; openai_api_key: string; agent_model: string }>,
): Promise<SettingsView> {
  const res = await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`settings update failed: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Type-check via build**

Run: `cd frontend && npm run build`
Expected: build succeeds (page.tsx still compiles — nothing removed from the old API surface).

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(frontend): API client — capabilities, artifacts, opportunities, shared SSE streamer"
```

---

### Task 9: Frontend UI — capability bar + artifacts in canvas

**Files:**
- Modify: `frontend/app/page.tsx` (full replacement of the `Home` component and additions below; `Bubble` and `SettingsBadge` stay as they are)

- [ ] **Step 1: Replace the imports and `Home` component in `frontend/app/page.tsx`**

Replace the import block at the top with:

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AgentEvent,
  Artifact,
  Capability,
  Note,
  Opportunity,
  SettingsView,
  fetchArtifacts,
  fetchCapabilities,
  fetchNotes,
  fetchOpportunities,
  getSettings,
  invokeCapability,
  streamChat,
  updateSettings,
} from "@/lib/api";
```

Replace the whole `Home` component with:

```tsx
type ChatItem =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string }
  | { kind: "tool"; text: string }
  | { kind: "error"; text: string };

const BADGE: Record<Artifact["review_status"], string> = {
  draft: "bg-slate-200 text-slate-700",
  needs_review: "bg-amber-100 text-amber-800",
  approved: "bg-emerald-100 text-emerald-800",
};

export default function Home() {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [notes, setNotes] = useState<Note[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [caps, setCaps] = useState<Capability[]>([]);
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [selectedOpp, setSelectedOpp] = useState("");
  const [settings, setSettings] = useState<SettingsView | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const refreshCanvas = useCallback(async () => {
    try {
      const [n, a, o] = await Promise.all([
        fetchNotes(),
        fetchArtifacts(),
        fetchOpportunities(),
      ]);
      setNotes(n);
      setArtifacts(a);
      setOpps(o);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    getSettings().then(setSettings).catch(() => setSettings(null));
    fetchCapabilities().then(setCaps).catch(() => setCaps([]));
    refreshCanvas();
  }, [refreshCanvas]);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [items]);

  const makeOnEvent = useCallback(() => {
    return (e: AgentEvent) => {
      setItems((prev) => {
        const next = [...prev];
        if (e.type === "token") {
          // append to the trailing assistant bubble
          for (let i = next.length - 1; i >= 0; i--) {
            if (next[i].kind === "assistant") {
              next[i] = { kind: "assistant", text: next[i].text + e.content };
              break;
            }
          }
        } else if (e.type === "tool_use") {
          let name = e.content;
          try {
            name = JSON.parse(e.content).name ?? e.content;
          } catch {
            /* keep raw */
          }
          next.push({ kind: "tool", text: `🔧 ${name}` });
          next.push({ kind: "assistant", text: "" });
        } else if (e.type === "error") {
          next.push({ kind: "error", text: e.content });
        }
        return next;
      });
      if (e.type === "tool_result" || e.type === "result") refreshCanvas();
    };
  }, [refreshCanvas]);

  const runStream = useCallback(
    async (
      bubble: string,
      start: (onEvent: (e: AgentEvent) => void) => Promise<void>,
    ) => {
      if (running) return;
      setRunning(true);
      setItems((prev) => [
        ...prev,
        { kind: "user", text: bubble },
        { kind: "assistant", text: "" },
      ]);
      try {
        await start(makeOnEvent());
      } catch (err) {
        setItems((prev) => [...prev, { kind: "error", text: String(err) }]);
      } finally {
        setRunning(false);
        refreshCanvas();
      }
    },
    [running, makeOnEvent, refreshCanvas],
  );

  const send = useCallback(async () => {
    const prompt = input.trim();
    if (!prompt) return;
    setInput("");
    await runStream(prompt, (onEvent) => streamChat(prompt, onEvent));
  }, [input, runStream]);

  const invoke = useCallback(
    async (cap: Capability) => {
      const text = input.trim();
      if (cap.requires_input && !text) {
        setItems((prev) => [
          ...prev,
          {
            kind: "error",
            text: `“${cap.label}” needs input — paste it into the message box first.`,
          },
        ]);
        return;
      }
      if (cap.requires_input) setInput("");
      await runStream(`▶ ${cap.label}`, (onEvent) =>
        invokeCapability(
          cap.name,
          { opportunity_id: selectedOpp || undefined, input: text },
          onEvent,
        ),
      );
    },
    [input, selectedOpp, runStream],
  );

  return (
    <main className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b bg-white px-4 py-3">
        <h1 className="text-lg font-semibold">Opportunity Hunter</h1>
        <SettingsBadge settings={settings} onSaved={setSettings} />
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        {/* Chat pane */}
        <section className="flex min-h-0 flex-1 flex-col border-r">
          {/* Capability bar */}
          <div className="flex flex-wrap items-center gap-2 border-b bg-slate-50 px-3 py-2">
            <select
              className="rounded border px-2 py-1 text-xs"
              value={selectedOpp}
              onChange={(e) => setSelectedOpp(e.target.value)}
            >
              <option value="">— opportunity —</option>
              {opps.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.organization ? `${o.organization} — ${o.title}` : o.title}
                </option>
              ))}
            </select>
            {caps.map((c) => (
              <button
                key={c.name}
                title={c.description}
                className="rounded bg-slate-200 px-2 py-1 text-xs font-medium text-slate-800 hover:bg-slate-300 disabled:opacity-40"
                onClick={() => invoke(c)}
                disabled={running || (c.requires_opportunity && !selectedOpp)}
              >
                {c.label}
              </button>
            ))}
          </div>

          <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {items.length === 0 && (
              <p className="text-sm text-slate-500">
                Message the agent, or pick an opportunity and press a capability
                button. &ldquo;Add by paste&rdquo; uses whatever you&rsquo;ve typed
                in the message box.
              </p>
            )}
            {items.map((it, i) => (
              <Bubble key={i} item={it} />
            ))}
          </div>
          <div className="flex gap-2 border-t bg-white p-3">
            <input
              className="flex-1 rounded border px-3 py-2 text-sm"
              placeholder="Message the agent…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              disabled={running}
            />
            <button
              className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              onClick={send}
              disabled={running || !input.trim()}
            >
              {running ? "…" : "Send"}
            </button>
          </div>
        </section>

        {/* Canvas pane */}
        <section className="flex min-h-0 flex-1 flex-col bg-white">
          <div className="border-b px-4 py-2 text-sm font-medium text-slate-600">
            Canvas — Artifacts ({artifacts.length}) · Notes ({notes.length})
          </div>
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {artifacts.length === 0 && notes.length === 0 && (
              <p className="text-sm text-slate-400">
                Artifacts and notes the agent saves will appear here.
              </p>
            )}
            {artifacts.map((a) => (
              <article key={`a-${a.id}`} className="rounded border bg-slate-50 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold">{a.title}</h3>
                  <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                    {a.kind} v{a.version}
                  </span>
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${BADGE[a.review_status]}`}
                  >
                    {a.review_status.replace("_", " ")}
                  </span>
                </div>
                {a.provenance && (
                  <p className="mt-0.5 text-[11px] text-slate-400">{a.provenance}</p>
                )}
                <p className="mt-1 max-h-40 overflow-hidden whitespace-pre-wrap text-sm text-slate-700">
                  {a.body}
                </p>
              </article>
            ))}
            {notes.map((n) => (
              <article key={`n-${n.id}`} className="rounded border bg-slate-50 p-3">
                <h3 className="text-sm font-semibold">{n.title}</h3>
                <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{n.body}</p>
              </article>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
```

(`Bubble` and `SettingsBadge` below the component are unchanged.)

- [ ] **Step 2: Build to verify**

Run: `cd frontend && npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(frontend): capability bar + artifacts with review-status badges in canvas"
```

---

### Task 10: Live seam gate

**Files:**
- Create: `tests/test_career_pack_live.py`

- [ ] **Step 1: Write the gated live test**

Create `tests/test_career_pack_live.py`:

```python
"""Live seam gate (career pack): a REAL local-CLI agent session must discover
the repo-local career-pack plugin from an isolated session cwd, invoke the
fit-analysis skill, and follow its write-back contract.

Run: OH_RUN_LIVE_PROBE=1 uv run pytest tests/test_career_pack_live.py -v
Needs an authed local `claude` CLI. Deliberately NO OpenAI dependency:
fit-analysis works from the inlined profile block (no embedder needed).
"""

from __future__ import annotations

import os

import pytest
from sqlmodel import Session, select

from app import capabilities as caps
from app import services
from app.agent import runner
from app.db import engine
from app.models import Artifact, ArtifactKind, Decision, OpportunityType, Profile

pytestmark = pytest.mark.skipif(
    os.environ.get("OH_RUN_LIVE_PROBE") != "1",
    reason="live probe: set OH_RUN_LIVE_PROBE=1 (needs authed claude CLI)",
)


async def test_live_fit_analysis_writes_contracted_rows():
    with Session(engine) as s:
        opp = services.upsert_opportunity(
            s, type=OpportunityType.job, title="Staff ML Engineer",
            dedupe_key="live-fit-probe", organization="Acme AI",
            url=None, location="Remote (US)",
            summary="Own the PyTorch training platform; K8s-based MLOps; lead a small team.",
            source="manual",
            details={"seniority": "staff", "skills": ["pytorch", "kubernetes"]},
        )
        opp_id = opp.id
        s.add(Profile(
            headline="Staff ML Engineer — training platforms",
            summary="9 years building PyTorch training infrastructure on Kubernetes; led MLOps teams.",
            skills=["pytorch", "kubernetes", "mlops", "python"],
            target_titles=["Staff ML Engineer"],
            locations=["Remote"],
        ))
        s.commit()

    cap = caps.REGISTRY["fit-analysis"]
    with Session(engine) as s:
        opp = services.get_opportunity(s, opp_id)
        profile = s.exec(select(Profile)).first()
        prompt = caps.build_prompt(cap, opportunity=opp, profile=profile)

    # Real sdk_query (default query_fn) -> local claude CLI.
    events = [e async for e in runner.stream_run(prompt, model=None, api_key=None)]
    assert events[-1]["type"] == "status" and events[-1]["content"] == "completed", (
        f"run did not complete cleanly; last events: {events[-3:]}"
    )

    with Session(engine) as s:
        artifact = s.exec(
            select(Artifact).where(
                Artifact.opportunity_id == opp_id,
                Artifact.kind == ArtifactKind.fit_analysis,
            )
        ).first()
        assert artifact is not None, "skill never called save_artifact — seam FAILED"
        assert artifact.provenance == "career-pack:fit-analysis"
        assert artifact.version == 1
        assert len(artifact.body) > 200, "suspiciously thin analysis body"
        decision = s.exec(
            select(Decision).where(Decision.opportunity_id == opp_id)
        ).first()
        assert decision is not None, "skill never called record_decision — seam FAILED"
        assert decision.summary, "decision row has empty summary"
```

- [ ] **Step 2: Verify it skips offline**

Run: `uv run pytest tests/test_career_pack_live.py -v`
Expected: 1 skipped ("live probe: set OH_RUN_LIVE_PROBE=1 …")

- [ ] **Step 3: Run the live gate** (requires authed `claude` CLI on this machine)

Run: `OH_RUN_LIVE_PROBE=1 uv run pytest tests/test_career_pack_live.py -v`
Expected: PASS in roughly 1–3 minutes. **If it fails on skill discovery** (run
completes but no Skill tool call appears in events): first suspect the
`skills=` naming — try unqualified names (`fit-analysis` instead of
`career-pack:fit-analysis`) in `app/capabilities.py:SKILL_NAMES`; the
qualified form is what Claude Code uses for plugin skills, but verify against
the events log (`tool_use` events) rather than guessing.

- [ ] **Step 4: Commit**

```bash
git add tests/test_career_pack_live.py
git commit -m "test(career-pack): live seam gate — real CLI discovers plugin skill and writes rows"
```

---

### Task 11: Full verification + docs

- [ ] **Step 1: Run the entire suite**

Run: `uv run pytest -q`
Expected: all pass (≈110), 3 skipped (the three live probes), 0 failures.

- [ ] **Step 2: Frontend production build**

Run: `cd frontend && npm run build`
Expected: success.

- [ ] **Step 3: Mark the spec implemented**

In `docs/superpowers/specs/2026-06-11-career-pack-design.md`, change
`**Status:** Approved design` to `**Status:** Implemented (this plan), live gate <PASSED/pending>` — reflect the actual Task 9 outcome.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-06-11-career-pack-design.md
git commit -m "docs(spec): mark career-pack spec implemented"
```

Then follow superpowers:finishing-a-development-branch (merge to main is the
established pattern for this repo; full suite must be green first).
