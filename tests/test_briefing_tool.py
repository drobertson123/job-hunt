from __future__ import annotations

import pytest
from sqlmodel import Session

from app import briefing_service
from app.agent import tools
from app.db import engine
from app.models import Briefing, Opportunity, OpportunityType


@pytest.mark.asyncio
async def test_synthesize_briefing_tool_forwards_and_returns_ok(monkeypatch):
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        opp_id = opp.id

    seen = {}

    async def fake(session, *, opportunity_id, generated_run_id=None, **kw):
        seen["opportunity_id"] = opportunity_id
        b = Briefing(opportunity_id=opportunity_id, summary="x",
                     facts=[{"key": "why_fit", "question": "q", "answer": "a",
                             "confidence": 0.5, "source": None}])
        session.add(b)
        session.commit()
        session.refresh(b)
        return b

    monkeypatch.setattr(briefing_service, "synthesize_briefing", fake)
    res = await tools.synthesize_briefing.handler({"opportunity_id": opp_id})
    assert seen["opportunity_id"] == opp_id
    assert res["content"][0]["type"] == "text"
