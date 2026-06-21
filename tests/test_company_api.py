from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import Opportunity, OpportunityType


def test_list_companies_endpoint(client):
    with Session(engine) as s:
        services.upsert_company(s, name="Acme")
    res = client.get("/api/companies")
    assert res.status_code == 200 and any(c["name"] == "Acme" for c in res.json())


def test_backfill_endpoint_links_and_detail_includes_company(client):
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role", organization="Initech")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        oid = opp.id

    res = client.post("/api/companies/backfill")
    assert res.status_code == 200
    assert res.json()["opportunities_linked"] == 1

    detail = client.get(f"/api/opportunities/{oid}").json()
    assert "company" in detail and detail["company"] is not None
    assert detail["company"]["name"] == "Initech"
