"""Normalizer probe — reused-skill free-form artifact -> structured job rows.

Two layers:
  * deterministic plumbing tests (fake query_fn) — no CLI / network / key needed;
  * a live probe (real local `claude` CLI session) gated on OH_RUN_LIVE_PROBE.

Extraction runs through the Claude Agent SDK (CLI auth), not the Anthropic API,
so the normalizer prompts for JSON and validates it with Pydantic itself.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from claude_agent_sdk import AssistantMessage, TextBlock
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


def _fake_query(reply_text: str, calls: list[dict]):
    """Fake Agent SDK query_fn: records (prompt, options) and replies with text."""

    async def fake(*, prompt, options) -> AsyncIterator:
        calls.append({"prompt": prompt, "options": options})
        yield AssistantMessage(content=[TextBlock(text=reply_text)], model="fake-model")

    return fake


async def test_normalize_artifact_parses_json_reply_and_passes_prompt():
    reply = (
        "Here you go:\n```json\n"
        '{"opportunities": [{"title": "Staff ML Engineer", "organization": "Acme AI"}]}'
        "\n```"
    )
    calls: list[dict] = []

    out = await normalize_artifact(
        "some free-form markdown", query_fn=_fake_query(reply, calls), model="test-model"
    )

    assert isinstance(out, NormalizerResult)
    assert len(out.opportunities) == 1
    assert out.opportunities[0].title == "Staff ML Engineer"
    assert out.opportunities[0].organization == "Acme AI"
    assert calls[0]["options"].model == "test-model"
    assert "some free-form markdown" in calls[0]["prompt"]


async def test_normalize_artifact_defaults_model_from_config():
    calls: list[dict] = []

    await normalize_artifact(
        "md", query_fn=_fake_query('{"opportunities": []}', calls)
    )

    from app.config import get_config

    assert calls[0]["options"].model == get_config().default_agent_model


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
    not os.environ.get("OH_RUN_LIVE_PROBE"),
    reason="set OH_RUN_LIVE_PROBE=1 to run the live local-CLI probe (needs an authed `claude` CLI)",
)
async def test_live_probe_extracts_correct_job_row_from_fixture():
    markdown = FIXTURE.read_text()

    result = await normalize_artifact(markdown)

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
