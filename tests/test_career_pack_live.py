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
