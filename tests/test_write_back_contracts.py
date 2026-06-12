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
    update_pipeline_status,
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
    OpportunityType,
    PipelineStage,
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
        by_key = {r.dedupe_key: r.summary for r in rows}
        assert by_key["https://grants.example/a"] == "updated"
        assert by_key["https://grants.example/b"] == "Matches profile: ML platform work."


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
