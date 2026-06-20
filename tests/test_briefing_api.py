from __future__ import annotations

from sqlmodel import Session

from app import briefing_service
from app.db import engine
from app.models import Briefing, Opportunity, OpportunityType


def _make_opp() -> str:
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        return opp.id


def test_synthesize_endpoint_returns_briefing(client, monkeypatch):
    opp_id = _make_opp()

    async def fake(session, *, opportunity_id, generated_run_id=None, **kw):
        b = Briefing(opportunity_id=opportunity_id, summary="ok",
                     facts=[{"key": "why_fit", "question": "q", "answer": "a",
                             "confidence": 0.9, "source": None}])
        session.add(b)
        session.commit()
        session.refresh(b)
        return b

    monkeypatch.setattr(briefing_service, "synthesize_briefing", fake)
    res = client.post(f"/api/opportunities/{opp_id}/briefing/synthesize")
    assert res.status_code == 200
    assert res.json()["summary"] == "ok"


def test_get_briefing_endpoint_and_detail_include(client):
    opp_id = _make_opp()
    # none yet
    assert client.get(f"/api/opportunities/{opp_id}/briefing").json() is None
    with Session(engine) as s:
        s.add(Briefing(opportunity_id=opp_id, summary="hi", facts=[]))
        s.commit()
    got = client.get(f"/api/opportunities/{opp_id}/briefing")
    assert got.status_code == 200 and got.json()["summary"] == "hi"
    detail = client.get(f"/api/opportunities/{opp_id}")
    assert "briefing" in detail.json() and detail.json()["briefing"]["summary"] == "hi"


def test_synthesize_missing_opportunity_404(client):
    res = client.post("/api/opportunities/nope/briefing/synthesize")
    assert res.status_code == 404
