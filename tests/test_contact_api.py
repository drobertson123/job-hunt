from __future__ import annotations

from sqlmodel import Session

from app.db import engine
from app.models import Opportunity, OpportunityType


def _opp_id() -> str:
    with Session(engine) as s:
        o = Opportunity(type=OpportunityType.job, title="Role")
        s.add(o)
        s.commit()
        s.refresh(o)
        return o.id


def test_post_then_get_contacts(client):
    oid = _opp_id()
    created = client.post("/api/contacts", json={"name": "Pat Recruiter",
                                                 "opportunity_id": oid, "role": "Recruiter"})
    assert created.status_code == 200 and created.json()["name"] == "Pat Recruiter"
    listed = client.get("/api/contacts", params={"opportunity_id": oid})
    assert listed.status_code == 200 and len(listed.json()) == 1


def test_opportunity_detail_includes_contacts(client):
    oid = _opp_id()
    client.post("/api/contacts", json={"name": "X", "opportunity_id": oid})
    detail = client.get(f"/api/opportunities/{oid}").json()
    assert "contacts" in detail and len(detail["contacts"]) == 1
