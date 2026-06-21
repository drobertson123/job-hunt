from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.agent import tools
from app.db import engine
from app.models import Contact, Opportunity, OpportunityType


@pytest.mark.asyncio
async def test_record_contact_tool_creates_row():
    with Session(engine) as s:
        o = Opportunity(type=OpportunityType.job, title="Role")
        s.add(o)
        s.commit()
        s.refresh(o)
        oid = o.id
    res = await tools.record_contact.handler(
        {"name": "Dana Lead", "opportunity_id": oid, "role": "Hiring Manager"}
    )
    assert res["content"][0]["type"] == "text"
    with Session(engine) as s:
        rows = s.exec(select(Contact).where(Contact.opportunity_id == oid)).all()
    assert len(rows) == 1 and rows[0].name == "Dana Lead"
