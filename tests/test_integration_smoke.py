"""End-to-end integration proof (goal #10).

These assert that the features built this cycle COMPOSE correctly across module
boundaries — the cross-feature flows no single per-feature test covers:
  * a scheduled interview surfaces in the weekly review AND exports as .ics
  * an opportunity's pipeline stage drives which weekly bucket it lands in,
    and "create this week's actions" is idempotent
  * opting a job source into auto-search makes the scheduler consider it due
  * the full capability set (incl. the email-analyser added this cycle) is
    reachable via the API

All run against the isolated test DB (conftest fixtures), never real data.
"""

from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session

from app import search_scheduler as sched
from app.db import engine
from app.models import Opportunity, OpportunityType, PipelineStage, _utcnow


def test_all_capabilities_reachable_via_api(client):
    names = {c["name"] for c in client.get("/api/capabilities").json()}
    assert "email-analyser" in names
    assert "cover-letter" in names
    assert len(names) == 15


def test_interview_flows_into_weekly_review_and_exports_ics(client):
    starts = (_utcnow() + timedelta(days=2)).replace(microsecond=0)
    created = client.post(
        "/api/interviews",
        json={"title": "Final round", "starts_at": starts.isoformat(), "kind": "final"},
    )
    assert created.status_code == 200, created.text
    iid = created.json()["id"]

    weekly = client.get("/api/weekly-review").json()
    assert any(i["id"] == iid for i in weekly["interviews_this_week"])

    ics = client.get(f"/api/interviews/{iid}.ics")
    assert ics.status_code == 200
    assert "BEGIN:VEVENT" in ics.text and "Final round" in ics.text

    assert client.delete(f"/api/interviews/{iid}").status_code == 204


def test_opportunity_stage_drives_weekly_buckets_and_actions_idempotent(client):
    with Session(engine) as s:
        new = Opportunity(type=OpportunityType.job, title="Fresh lead", stage=PipelineStage.new)
        qual = Opportunity(
            type=OpportunityType.job, title="Ready to apply", stage=PipelineStage.qualifying
        )
        s.add(new)
        s.add(qual)
        s.commit()
        s.refresh(new)
        s.refresh(qual)
        nid, qid = new.id, qual.id

    weekly = client.get("/api/weekly-review").json()
    assert any(o["id"] == nid for o in weekly["to_identify"])
    assert any(o["id"] == qid for o in weekly["to_apply"])

    first = client.post("/api/weekly-review/actions").json()["created"]
    assert first >= 2
    second = client.post("/api/weekly-review/actions").json()["created"]
    assert second == 0  # idempotent — no duplicate actions on a second run


def test_job_source_optin_makes_it_due_for_the_scheduler(client):
    created = client.post(
        "/api/job-sources",
        json={"name": "Board X", "saved_query": "ml roles", "auto_search": True},
    )
    assert created.status_code == 200
    sid = created.json()["id"]

    with Session(engine) as s:
        due = sched.due_job_sources(s, now=_utcnow(), interval_hours=24)
    assert any(d.id == sid for d in due)

    # not opted in → not due
    off = client.post(
        "/api/job-sources",
        json={"name": "Board Y", "saved_query": "data roles", "auto_search": False},
    ).json()["id"]
    with Session(engine) as s:
        due_ids = {d.id for d in sched.due_job_sources(s, now=_utcnow(), interval_hours=24)}
    assert off not in due_ids
