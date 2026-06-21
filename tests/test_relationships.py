from sqlmodel import Session

from app.db import engine
from app import relationships_service as rs, services
from app.models import Company, Opportunity, OpportunityType


def test_relationships_cluster_with_contact_and_role():
    with Session(engine) as s:
        co = Company(name="Stripe")
        s.add(co); s.commit(); s.refresh(co)
        services.add_contact(s, name="Jane Smith", role="EM", organization="Stripe", )
        s.add(Opportunity(type=OpportunityType.job, title="Staff Eng", organization="Stripe"))
        s.commit()
        out = rs.compute_relationships(s)
    stripe = next((c for c in out["clusters"] if c["name"] == "Stripe"), None)
    assert stripe is not None
    assert any(p["name"] == "Jane Smith" for p in stripe["contacts"])
    assert any(o["title"] == "Staff Eng" for o in stripe["opportunities"])
    assert out["warm_intro_count"] >= 1


def test_relationships_endpoint(client):
    r = client.get("/api/relationships")
    assert r.status_code == 200
    assert "clusters" in r.json() and "warm_intro_count" in r.json()
