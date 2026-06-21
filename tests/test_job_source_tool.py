from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.agent import tools
from app.db import engine
from app.models import JobSource, JobSourceKind, Opportunity, OpportunityType


@pytest.mark.asyncio
async def test_record_job_source_tool_creates_with_default_kind():
    res = await tools.record_job_source.handler({"name": "AngelList"})
    assert res["content"][0]["type"] == "text"
    with Session(engine) as s:
        row = s.exec(select(JobSource).where(JobSource.name == "AngelList")).one()
    assert row.kind == JobSourceKind.other


@pytest.mark.asyncio
async def test_record_job_source_tool_links_opportunity():
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        oid = opp.id
    await tools.record_job_source.handler(
        {"name": "Referral", "kind": "referral", "link_opportunity_id": oid}
    )
    with Session(engine) as s:
        linked = s.get(Opportunity, oid)
    assert linked.source_id is not None
