from datetime import datetime

from sqlmodel import Session

from app.db import engine
from app import metrics_service as ms
from app.models import Application, ApplicationStatus, Opportunity, OpportunityType


def _seed():
    with Session(engine) as s:
        o = Opportunity(type=OpportunityType.job, title="O", source="linkedin", stage="active")
        s.add(o); s.commit(); s.refresh(o)
        for st in [ApplicationStatus.submitted, ApplicationStatus.under_review,
                   ApplicationStatus.interviewing, ApplicationStatus.offer]:
            s.add(Application(opportunity_id=o.id, status=st))
        s.commit()


def test_compute_metrics_funnel_and_kpis():
    _seed()
    now = datetime(2026, 6, 21, 12, 0)
    with Session(engine) as s:
        m = ms.compute_metrics(s, now=now)
    assert m["kpis"]["total_applications"] == 4
    f = {x["label"]: x["count"] for x in m["funnel"]}
    assert f["Applied"] == 4 and f["Screening"] == 3 and f["Interview"] == 2 and f["Offer"] == 1
    assert len(m["volume"]) == 8
    assert any(src["source"] == "linkedin" for src in m["sources"])


def test_metrics_endpoint(client):
    r = client.get("/api/metrics")
    assert r.status_code == 200
    for k in ("kpis", "funnel", "volume", "sources"):
        assert k in r.json()
