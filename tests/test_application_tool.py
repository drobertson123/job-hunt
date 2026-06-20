from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.agent import tools
from app.db import engine
from app.models import Application, ApplicationStatus, Opportunity, OpportunityType


def _make_opp() -> str:
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        return opp.id


@pytest.mark.asyncio
async def test_record_application_tool_creates_row():
    opp_id = _make_opp()
    res = await tools.record_application.handler(
        {"opportunity_id": opp_id, "status": "submitted",
         "portal_url": "https://boards.greenhouse.io/x"}
    )
    assert res["content"][0]["type"] == "text"
    with Session(engine) as s:
        rows = s.exec(select(Application).where(Application.opportunity_id == opp_id)).all()
    assert len(rows) == 1 and rows[0].status == ApplicationStatus.submitted


@pytest.mark.asyncio
async def test_record_application_tool_bad_status_defaults_draft():
    opp_id = _make_opp()
    await tools.record_application.handler({"opportunity_id": opp_id, "status": "bogus"})
    with Session(engine) as s:
        row = s.exec(select(Application).where(Application.opportunity_id == opp_id)).one()
    assert row.status == ApplicationStatus.draft
