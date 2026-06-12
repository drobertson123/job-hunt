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
