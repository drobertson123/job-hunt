from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.agent import tools
from app.db import engine
from app.models import Company


@pytest.mark.asyncio
async def test_record_company_tool_creates_and_enriches():
    res = await tools.record_company.handler({"name": "Wayne Ent", "industry": "Defense"})
    assert res["content"][0]["type"] == "text"
    with Session(engine) as s:
        row = s.exec(select(Company).where(Company.name == "Wayne Ent")).one()
        cid = row.id
        assert row.industry == "Defense"
    # enrich by id without wiping industry
    await tools.record_company.handler({"name": "Wayne Ent", "company_id": cid,
                                        "ats_vendor": "Lever"})
    with Session(engine) as s:
        row = s.get(Company, cid)
        assert row.industry == "Defense" and row.ats_vendor == "Lever"


@pytest.mark.asyncio
async def test_record_company_tool_links_opportunity():
    from app.models import Opportunity, OpportunityType
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        oid = opp.id
    await tools.record_company.handler({"name": "Wayne Ent", "link_opportunity_id": oid})
    with Session(engine) as s:
        linked = s.get(Opportunity, oid)
        assert linked.company_id is not None
