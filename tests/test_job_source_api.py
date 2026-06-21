"""Test job sources API endpoints."""
from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import JobSourceKind, Opportunity, OpportunityType


def test_list_job_sources_endpoint(client):
    with Session(engine) as s:
        services.upsert_job_source(s, name="LinkedIn")
    res = client.get("/api/job-sources")
    assert res.status_code == 200 and any(j["name"] == "LinkedIn" for j in res.json())


def test_opportunity_detail_includes_source(client):
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        oid = opp.id
        services.upsert_job_source(s, name="Referral", kind=JobSourceKind.referral,
                                   link_opportunity_id=oid)

    detail = client.get(f"/api/opportunities/{oid}").json()
    assert "source" in detail and detail["source"] is not None
    assert detail["source"]["name"] == "Referral"
