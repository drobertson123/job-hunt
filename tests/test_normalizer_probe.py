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
