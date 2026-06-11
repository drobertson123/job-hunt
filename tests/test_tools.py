"""Tests for the in-process MCP write-back tool handlers (no API key needed)."""

from __future__ import annotations

from sqlmodel import Session, select

from app.agent import tools
from app.agent.tools import current_run_id
from app.db import engine
from app.models import Action, Artifact, Opportunity, PipelineStage


async def test_save_opportunity_creates_and_dedupes():
    r1 = await tools.save_opportunity.handler(
        {"type": "job", "title": "Tool Eng", "dedupe_key": "tool-eng", "details": {"salary": "1"}}
    )
    assert "Saved opportunity" in r1["content"][0]["text"]
    r2 = await tools.save_opportunity.handler(
        {"type": "job", "title": "Tool Eng", "dedupe_key": "tool-eng", "details": {"loc": "remote"}}
    )
    assert "Saved opportunity" in r2["content"][0]["text"]

    with Session(engine) as s:
        rows = s.exec(
            select(Opportunity).where(Opportunity.dedupe_key == "tool-eng")
        ).all()
        assert len(rows) == 1
        assert rows[0].details == {"salary": "1", "loc": "remote"}


async def test_update_pipeline_status_tool():
    with Session(engine) as s:
        from app import services
        from app.models import OpportunityType

        opp = services.upsert_opportunity(s, type=OpportunityType.business, title="Stage tool")
        opp_id = opp.id

    res = await tools.update_pipeline_status.handler(
        {"opportunity_id": opp_id, "stage": "active", "rationale": "go"}
    )
    assert "active" in res["content"][0]["text"]
    with Session(engine) as s:
        assert s.get(Opportunity, opp_id).stage == PipelineStage.active


async def test_update_pipeline_status_unknown_opportunity_is_error():
    res = await tools.update_pipeline_status.handler(
        {"opportunity_id": "does-not-exist", "stage": "active"}
    )
    assert res.get("is_error") is True


async def test_record_action_tool_parses_due_date():
    res = await tools.record_action.handler(
        {"title": "Email recruiter", "kind": "followup", "due_at": "2026-01-02T09:00:00Z"}
    )
    assert "Recorded action" in res["content"][0]["text"]
    with Session(engine) as s:
        action = s.exec(
            select(Action).where(Action.title == "Email recruiter")
        ).first()
        assert action is not None and action.due_at is not None


async def test_save_artifact_tool_attributes_run_and_versions():
    token = current_run_id.set("run-xyz")
    try:
        await tools.save_artifact.handler(
            {"title": "Brief", "body": "a", "kind": "research_brief"}
        )
        await tools.save_artifact.handler(
            {"title": "Brief", "body": "b", "kind": "research_brief"}
        )
    finally:
        current_run_id.reset(token)

    with Session(engine) as s:
        arts = s.exec(select(Artifact).where(Artifact.title == "Brief")).all()
        assert {a.version for a in arts} == {1, 2}
        assert all(a.run_id == "run-xyz" for a in arts)
