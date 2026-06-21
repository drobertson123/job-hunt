from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.agent import tools
from app.db import engine
from app.models import CommChannel, CommDirection, Communication, Opportunity, OpportunityType


def _opp_id() -> str:
    with Session(engine) as s:
        o = Opportunity(type=OpportunityType.job, title="Role")
        s.add(o)
        s.commit()
        s.refresh(o)
        return o.id


@pytest.mark.asyncio
async def test_record_communication_tool_creates_row():
    oid = _opp_id()
    res = await tools.record_communication.handler(
        {"opportunity_id": oid, "direction": "inbound", "channel": "linkedin",
         "subject": "Hi"}
    )
    assert res["content"][0]["type"] == "text"
    with Session(engine) as s:
        rows = s.exec(select(Communication).where(Communication.opportunity_id == oid)).all()
    assert len(rows) == 1
    assert rows[0].direction == CommDirection.inbound and rows[0].channel == CommChannel.linkedin


@pytest.mark.asyncio
async def test_record_communication_tool_bad_enums_fall_back():
    oid = _opp_id()
    await tools.record_communication.handler(
        {"opportunity_id": oid, "direction": "??", "channel": "??"}
    )
    with Session(engine) as s:
        row = s.exec(select(Communication).where(Communication.opportunity_id == oid)).one()
    assert row.direction == CommDirection.outbound and row.channel == CommChannel.other
