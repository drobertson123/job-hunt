# Normalizer Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that a reused skill's free-form markdown artifact, run through an Anthropic `messages.parse` normalizer and persisted, yields correct structured `job` Opportunity rows in SQLite.

**Architecture:** A standalone, DB-decoupled module `app/agent/normalizer.py` exposes (1) Pydantic output schemas, (2) `normalize_artifact()` — a single `client.messages.parse(...)` call with an injectable client, and (3) `persist_normalized()` — a bridge that maps each normalized job through the existing `services.upsert_opportunity`. Two test layers: a live probe (real API, auto-skips without a key) and a deterministic stubbed-client test.

**Tech Stack:** Python 3.12, `anthropic` SDK (structured outputs via `messages.parse` + Pydantic), SQLModel/SQLite, pytest + pytest-asyncio, `uv`.

---

## Spec

Implements `docs/superpowers/specs/2026-06-10-normalizer-probe-design.md`.

## Implementation Notes (refinements agreed during planning)

- **`details` is a typed sub-model, not a free dict, in the extraction schema.** Anthropic
  structured outputs build a strict JSON schema from the Pydantic model; an arbitrary
  `dict[str, Any]` would become a loose `object` that strict structured-output schemas reject.
  We model the known job sub-fields (`salary`, `seniority`, `employment_type`, `skills`) as a
  `JobDetails` model and dump it to a plain dict (`exclude_none=True`) when persisting — so the
  `Opportunity.details` JSON column still receives a free dict, honoring the spec's intent.
- **`normalize_artifact` stays DB-decoupled.** It defaults the model from
  `get_config().default_agent_model` (== `claude-sonnet-4-6`) rather than reaching into the DB.
  Wiring `settings_service.resolve_agent_model` in is a one-line call-site change deferred to
  integration (Phase 2/3); the probe does not need it and keeping the normalizer pure makes it
  trivially testable.

## File Structure

- **Create** `app/agent/normalizer.py` — schemas (`JobDetails`, `NormalizedJob`,
  `NormalizerResult`), `dedupe_key_for()`, `normalize_artifact()`, `persist_normalized()`.
- **Create** `tests/fixtures/career_helper_research_brief.md` — one representative free-form
  research-brief artifact (single company + role).
- **Create** `tests/test_normalizer_probe.py` — stubbed plumbing tests + live probe test.
- **Modify** `pyproject.toml` — add the `anthropic` dependency (via `uv add`).

---

## Task 1: Add the `anthropic` dependency

**Files:**
- Modify: `pyproject.toml` (dependencies array)

- [ ] **Step 1: Add the dependency with uv**

Run:
```bash
uv add anthropic
```
Expected: resolves and installs `anthropic`; `pyproject.toml` `dependencies` now lists
`anthropic` and `uv.lock` is updated.

- [ ] **Step 2: Verify it imports and exposes structured-output parse**

Run:
```bash
uv run python -c "import anthropic; c = anthropic.Anthropic; assert hasattr(anthropic.resources.messages.Messages, 'parse'); print('anthropic OK', anthropic.__version__)"
```
Expected: prints `anthropic OK <version>` with no error. (If the `assert` path differs by
version, the fallback check `uv run python -c "import anthropic; print(anthropic.__version__)"`
must still succeed.)

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add anthropic SDK for the normalizer probe"
```

---

## Task 2: Normalizer schemas + dedupe key helper

**Files:**
- Create: `app/agent/normalizer.py`
- Test: `tests/test_normalizer_probe.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_normalizer_probe.py`:

```python
"""Normalizer probe — reused-skill free-form artifact -> structured job rows.

Two layers:
  * deterministic plumbing tests (stubbed client) — no API key needed;
  * a live probe (real messages.parse) that auto-skips without ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app.agent.normalizer import (
    JobDetails,
    NormalizedJob,
    NormalizerResult,
    dedupe_key_for,
    normalize_artifact,
    persist_normalized,
)
from app.db import engine
from app.models import Opportunity, OpportunityType

FIXTURE = Path(__file__).parent / "fixtures" / "career_helper_research_brief.md"


def test_dedupe_key_prefers_explicit_then_falls_back_to_org_title_slug():
    explicit = NormalizedJob(title="X", organization="Y", dedupe_key="given-key")
    assert dedupe_key_for(explicit) == "given-key"

    derived = NormalizedJob(title="Staff ML Engineer", organization="Acme AI")
    assert dedupe_key_for(derived) == "acme-ai-staff-ml-engineer"

    title_only = NormalizedJob(title="Solo Role!!")
    assert dedupe_key_for(title_only) == "solo-role"


def test_schema_defaults():
    job = NormalizedJob(title="Only Title")
    assert job.source == "career-helper"
    assert job.dedupe_key is None
    assert isinstance(job.details, JobDetails)
    assert job.details.skills == []
    assert NormalizerResult().opportunities == []
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_normalizer_probe.py::test_dedupe_key_prefers_explicit_then_falls_back_to_org_title_slug -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agent.normalizer'`
(or `ImportError`).

- [ ] **Step 3: Write minimal implementation**

Create `app/agent/normalizer.py`:

```python
"""Reused-skill normalizer — free-form markdown artifact -> structured job rows.

Reused MIT skills (e.g. the career-helper) emit free-form markdown, NOT calls to
our in-process MCP write-back tools. This module converts that free-form output
into structured `Opportunity` rows via a single Anthropic `messages.parse` call,
then persists them through the same service layer the authored-skill seam uses.

The module is DB-decoupled: `normalize_artifact` takes an injectable client and a
model name (defaulting to the configured agent model) so it is trivially testable
and carries no database dependency. `persist_normalized` is the only DB-aware part.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field
from sqlmodel import Session

from app import services
from app.config import get_config
from app.models import Opportunity, OpportunityType


class JobDetails(BaseModel):
    """Type-specific job fields, mirrored from the Opportunity.details convention."""

    salary: str | None = None
    seniority: str | None = None
    employment_type: str | None = None
    skills: list[str] = Field(default_factory=list)


class NormalizedJob(BaseModel):
    """One job opportunity extracted from a free-form artifact.

    Field names map 1:1 onto services.upsert_opportunity keyword arguments.
    """

    title: str
    organization: str | None = None
    url: str | None = None
    location: str | None = None
    summary: str | None = None
    source: str = "career-helper"
    dedupe_key: str | None = None
    details: JobDetails = Field(default_factory=JobDetails)


class NormalizerResult(BaseModel):
    """Top-level structured-output schema: zero or more job opportunities."""

    opportunities: list[NormalizedJob] = Field(default_factory=list)


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _SLUG_RE.sub("-", text.strip().lower()).strip("-")


def dedupe_key_for(job: NormalizedJob) -> str:
    """Stable idempotency key: explicit key wins, else org+title slug, else title slug."""
    if job.dedupe_key:
        return job.dedupe_key
    parts = [p for p in (job.organization, job.title) if p]
    return _slug(" ".join(parts)) if parts else _slug(job.title)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/test_normalizer_probe.py::test_dedupe_key_prefers_explicit_then_falls_back_to_org_title_slug tests/test_normalizer_probe.py::test_schema_defaults -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/agent/normalizer.py tests/test_normalizer_probe.py
git commit -m "feat(normalizer): schemas + dedupe key helper"
```

---

## Task 3: `normalize_artifact` with an injectable client

**Files:**
- Modify: `app/agent/normalizer.py`
- Test: `tests/test_normalizer_probe.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_normalizer_probe.py`:

```python
class _FakeMessages:
    """Stand-in for client.messages with a parse() that returns a canned result."""

    def __init__(self, result: NormalizerResult):
        self._result = result
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(parsed_output=self._result)


class _FakeClient:
    def __init__(self, result: NormalizerResult):
        self.messages = _FakeMessages(result)


def test_normalize_artifact_returns_parsed_output_and_passes_schema():
    result = NormalizerResult(
        opportunities=[NormalizedJob(title="Staff ML Engineer", organization="Acme AI")]
    )
    client = _FakeClient(result)

    out = normalize_artifact("some free-form markdown", client=client, model="test-model")

    assert out is result
    call = client.messages.calls[0]
    assert call["model"] == "test-model"
    assert call["output_format"] is NormalizerResult
    assert "some free-form markdown" in call["messages"][0]["content"]


def test_normalize_artifact_defaults_model_from_config():
    result = NormalizerResult()
    client = _FakeClient(result)

    normalize_artifact("md", client=client)

    from app.config import get_config

    assert client.messages.calls[0]["model"] == get_config().default_agent_model
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_normalizer_probe.py::test_normalize_artifact_returns_parsed_output_and_passes_schema -v
```
Expected: FAIL with `ImportError: cannot import name 'normalize_artifact'` (it is imported at
the top of the test module but not yet defined).

- [ ] **Step 3: Write minimal implementation**

Append to `app/agent/normalizer.py`:

```python
_SYSTEM_INSTRUCTION = (
    "You convert a free-form career research artifact into structured job "
    "opportunities. Extract every distinct role described. For each, capture the "
    "role title, hiring organization, location, a one-paragraph summary, and any "
    "job details present (salary, seniority, employment type, key skills). If a "
    "field is absent in the artifact, omit it — never invent values."
)


def _build_prompt(markdown: str) -> str:
    return (
        f"{_SYSTEM_INSTRUCTION}\n\n"
        "Here is the artifact between the markers:\n"
        "<artifact>\n"
        f"{markdown}\n"
        "</artifact>"
    )


def _default_client() -> Any:
    import anthropic

    return anthropic.Anthropic()


def normalize_artifact(
    markdown: str,
    *,
    client: Any | None = None,
    model: str | None = None,
    max_tokens: int = 2048,
) -> NormalizerResult:
    """Run one free-form artifact through messages.parse into a NormalizerResult.

    `client` is injectable (tests pass a fake exposing `.messages.parse`). `model`
    defaults to the configured agent model; the normalizer holds no DB dependency.
    """
    if client is None:
        client = _default_client()
    if model is None:
        model = get_config().default_agent_model

    response = client.messages.parse(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": _build_prompt(markdown)}],
        output_format=NormalizerResult,
    )
    return response.parsed_output
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/test_normalizer_probe.py::test_normalize_artifact_returns_parsed_output_and_passes_schema tests/test_normalizer_probe.py::test_normalize_artifact_defaults_model_from_config -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/agent/normalizer.py tests/test_normalizer_probe.py
git commit -m "feat(normalizer): normalize_artifact with injectable client"
```

---

## Task 4: `persist_normalized` bridge to the system of record

**Files:**
- Modify: `app/agent/normalizer.py`
- Test: `tests/test_normalizer_probe.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_normalizer_probe.py`:

```python
def test_persist_normalized_writes_correct_job_rows():
    result = NormalizerResult(
        opportunities=[
            NormalizedJob(
                title="Staff ML Engineer",
                organization="Acme AI",
                location="Remote (US)",
                summary="Own the model-serving platform.",
                details=JobDetails(salary="$220k", seniority="staff", skills=["Python", "MLOps"]),
            )
        ]
    )

    with Session(engine) as s:
        rows = persist_normalized(s, result)

    assert len(rows) == 1
    opp_id = rows[0].id

    with Session(engine) as s:
        opp = s.get(Opportunity, opp_id)
        assert opp is not None
        assert opp.type == OpportunityType.job
        assert opp.title == "Staff ML Engineer"
        assert opp.organization == "Acme AI"
        assert opp.summary == "Own the model-serving platform."
        assert opp.dedupe_key == "acme-ai-staff-ml-engineer"
        assert opp.source == "career-helper"
        assert opp.details == {
            "salary": "$220k",
            "seniority": "staff",
            "skills": ["Python", "MLOps"],
        }


def test_persist_normalized_is_idempotent_on_dedupe_key():
    def make(summary: str) -> NormalizerResult:
        return NormalizerResult(
            opportunities=[
                NormalizedJob(title="Dedupe Role", organization="Dedupe Co", summary=summary)
            ]
        )

    with Session(engine) as s:
        persist_normalized(s, make("first"))
    with Session(engine) as s:
        persist_normalized(s, make("second"))

    with Session(engine) as s:
        rows = s.exec(
            select(Opportunity).where(Opportunity.dedupe_key == "dedupe-co-dedupe-role")
        ).all()
        assert len(rows) == 1
        assert rows[0].summary == "second"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_normalizer_probe.py::test_persist_normalized_writes_correct_job_rows -v
```
Expected: FAIL with `ImportError: cannot import name 'persist_normalized'`.

- [ ] **Step 3: Write minimal implementation**

Append to `app/agent/normalizer.py`:

```python
def persist_normalized(
    session: Session,
    result: NormalizerResult,
    *,
    source: str | None = None,
) -> list[Opportunity]:
    """Persist each normalized job as a `job` Opportunity via the service layer.

    Returns the upserted rows. `details` is dumped to a plain dict (dropping unset
    fields) so the Opportunity.details JSON column receives a free-form mapping.
    """
    rows: list[Opportunity] = []
    for job in result.opportunities:
        details = job.details.model_dump(exclude_none=True, exclude_defaults=True)
        opp = services.upsert_opportunity(
            session,
            type=OpportunityType.job,
            title=job.title,
            dedupe_key=dedupe_key_for(job),
            organization=job.organization,
            url=job.url,
            location=job.location,
            summary=job.summary,
            source=source or job.source,
            details=details,
        )
        rows.append(opp)
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/test_normalizer_probe.py::test_persist_normalized_writes_correct_job_rows tests/test_normalizer_probe.py::test_persist_normalized_is_idempotent_on_dedupe_key -v
```
Expected: 2 passed.

Note on the `details` assertion: `model_dump(exclude_none=True, exclude_defaults=True)` drops
`None` fields and fields left at their default. In the first test `salary`, `seniority`, and a
non-empty `skills` list are all set, so all three appear and `employment_type` (unset) is
omitted — matching the asserted dict exactly.

- [ ] **Step 5: Commit**

```bash
git add app/agent/normalizer.py tests/test_normalizer_probe.py
git commit -m "feat(normalizer): persist_normalized bridge to upsert_opportunity"
```

---

## Task 5: Representative fixture + live probe test

**Files:**
- Create: `tests/fixtures/career_helper_research_brief.md`
- Modify: `tests/test_normalizer_probe.py`

- [ ] **Step 1: Create the fixture**

Create `tests/fixtures/career_helper_research_brief.md` (a free-form artifact in the shape the
career-helper skill emits — prose + headings, NOT pre-structured fields):

```markdown
# Research Brief: Staff Machine Learning Engineer at Northwind Robotics

## Company Snapshot
Northwind Robotics is a Series C warehouse-automation company headquartered in
Boston, MA, with a remote-first engineering org across the US. ~450 employees;
last raised $120M in 2025. Their core product is an autonomous picking system.

## The Role
They're hiring a **Staff Machine Learning Engineer** to lead perception modeling
for their next-generation picking arm. The role is remote (US) with quarterly
on-sites in Boston. Reports to the Director of Autonomy.

Compensation is listed as $230,000–$265,000 base plus equity. This is a full-time,
permanent position at the staff level.

## What They Want
- Deep experience with computer-vision models in production robotics
- Strong Python; comfort with PyTorch and real-time inference optimization
- Track record leading ML projects end to end and mentoring engineers

## Why It's a Fit
The candidate's background in real-time perception and prior staff-level leadership
maps directly onto Northwind's perception roadmap. The remote arrangement suits
their constraints, and the comp band is above their current target.

## Open Questions
- What does the on-call rotation look like for production model incidents?
- Is there a clear staff -> principal progression path?
```

- [ ] **Step 2: Write the live probe test**

Append to `tests/test_normalizer_probe.py`:

```python
@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="live probe needs ANTHROPIC_API_KEY (real messages.parse call)",
)
def test_live_probe_extracts_correct_job_row_from_fixture():
    markdown = FIXTURE.read_text()

    result = normalize_artifact(markdown)

    assert len(result.opportunities) == 1, "fixture describes exactly one role"

    with Session(engine) as s:
        rows = persist_normalized(s, result, source="career-helper")
    opp_id = rows[0].id

    with Session(engine) as s:
        opp = s.get(Opportunity, opp_id)

    # The gate: correct STRUCTURED ROWS, not a rendered doc.
    assert opp is not None
    assert opp.type == OpportunityType.job
    assert opp.title and "engineer" in opp.title.lower()
    assert opp.organization and "northwind" in opp.organization.lower()
    assert opp.summary  # non-empty extracted summary
    assert opp.dedupe_key  # stable key present
    assert opp.source == "career-helper"
```

- [ ] **Step 3: Run the deterministic suite (live test skips without a key)**

Run:
```bash
uv run pytest tests/test_normalizer_probe.py -v
```
Expected: the four deterministic tests PASS; `test_live_probe_extracts_correct_job_row_from_fixture`
shows `SKIPPED` (no `ANTHROPIC_API_KEY` in the test env).

- [ ] **Step 4: Run the live probe against the real API (the actual de-risking)**

Run (uses your real key; costs a few tokens):
```bash
ANTHROPIC_API_KEY="$OH_ANTHROPIC_API_KEY" uv run pytest tests/test_normalizer_probe.py::test_live_probe_extracts_correct_job_row_from_fixture -v
```
(If your key lives elsewhere, substitute it. The point is to run this ONCE with a real key.)
Expected: PASS — confirming the model extracted a correct `job` row from the free-form fixture.
If it FAILS, capture the assertion and the extracted row; the failure is the probe's finding
(e.g. the prompt or schema needs adjustment), which is exactly what this task exists to surface.

- [ ] **Step 5: Run the full repo test suite (no regression)**

Run:
```bash
uv run pytest -q
```
Expected: all prior tests still pass plus the new deterministic ones (live probe skipped).

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/career_helper_research_brief.md tests/test_normalizer_probe.py
git commit -m "test(normalizer): representative fixture + live probe gate"
```

---

## Done When

- `app/agent/normalizer.py` exists with `JobDetails`, `NormalizedJob`, `NormalizerResult`,
  `dedupe_key_for`, `normalize_artifact`, `persist_normalized`.
- Four deterministic tests pass with no API key; the live probe passes once run with a real key
  and confirms a correct structured `job` row (correct `type`, non-empty `title`/`organization`/
  `summary`, stable `dedupe_key`) landed in SQLite.
- `anthropic` is a project dependency; `uv run pytest -q` is green.
