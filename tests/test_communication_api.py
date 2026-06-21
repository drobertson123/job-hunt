from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import CommChannel, CommDirection, Opportunity, OpportunityType


def _seed() -> str:
    with Session(engine) as s:
        o = Opportunity(type=OpportunityType.job, title="Role")
        s.add(o)
        s.commit()
        s.refresh(o)
        services.record_communication(s, direction=CommDirection.inbound,
                                      channel=CommChannel.email, opportunity_id=o.id,
                                      subject="hi")
        return o.id


def test_list_communications_endpoint(client):
    oid = _seed()
    res = client.get("/api/communications")
    assert res.status_code == 200 and len(res.json()) == 1
    res2 = client.get("/api/communications", params={"opportunity_id": oid})
    assert res2.status_code == 200 and len(res2.json()) == 1


def test_opportunity_detail_includes_communications(client):
    oid = _seed()
    body = client.get(f"/api/opportunities/{oid}").json()
    assert "communications" in body and len(body["communications"]) == 1
