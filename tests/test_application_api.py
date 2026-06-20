from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import Opportunity, OpportunityType


def _seed() -> str:
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        services.record_application(s, opportunity_id=opp.id, portal_url="https://x")
        return opp.id


def test_list_applications_endpoint(client):
    opp_id = _seed()
    res = client.get("/api/applications")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1 and data[0]["opportunity_id"] == opp_id

    res2 = client.get("/api/applications", params={"opportunity_id": opp_id})
    assert res2.status_code == 200 and len(res2.json()) == 1


def test_opportunity_detail_includes_applications(client):
    opp_id = _seed()
    res = client.get(f"/api/opportunities/{opp_id}")
    assert res.status_code == 200
    body = res.json()
    assert "applications" in body and len(body["applications"]) == 1
