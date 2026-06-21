from datetime import datetime, timedelta

from sqlmodel import Session

from app.db import engine
from app import services, weekly_review as wr
from app.models import (
    Opportunity, OpportunityType, PipelineStage, Application, Action,
    ActionKind, ActionStatus,
)


def _opp(stage, title="O", type_=OpportunityType.job):
    with Session(engine) as s:
        o = Opportunity(type=type_, title=title, stage=stage)
        s.add(o)
        s.commit()
        s.refresh(o)
        return o


def test_weekly_review_buckets_by_stage():
    now = datetime(2026, 6, 21, 12, 0)
    n = _opp(PipelineStage.new, "New one")
    q = _opp(PipelineStage.qualifying, "Qualify me")
    a = _opp(PipelineStage.active, "Applied")
    won = _opp(PipelineStage.won, "Won")
    with Session(engine) as s:
        plan = wr.weekly_review(s, now=now)
    ids = lambda b: {x["id"] for x in plan[b]}
    assert n.id in ids("to_identify")
    assert q.id in ids("to_apply")
    assert a.id in ids("to_follow_up")
    assert won.id not in ids("to_identify") | ids("to_apply") | ids("to_follow_up")


def test_to_apply_excludes_opps_with_application():
    now = datetime(2026, 6, 21, 12, 0)
    q = _opp(PipelineStage.qualifying, "Has app")
    with Session(engine) as s:
        s.add(Application(opportunity_id=q.id))
        s.commit()
        plan = wr.weekly_review(s, now=now)
    assert q.id not in {x["id"] for x in plan["to_apply"]}


def test_interviews_this_week_window():
    now = datetime(2026, 6, 21, 12, 0)
    with Session(engine) as s:
        soon = services.add_interview(s, title="Soon", starts_at=now + timedelta(days=2))
        far = services.add_interview(s, title="Far", starts_at=now + timedelta(days=30))
        plan = wr.weekly_review(s, now=now)
    iids = {x["id"] for x in plan["interviews_this_week"]}
    assert soon.id in iids and far.id not in iids


def test_create_weekly_actions_idempotent_and_no_activity_bump():
    now = datetime(2026, 6, 21, 12, 0)
    q = _opp(PipelineStage.qualifying, "Apply target")
    with Session(engine) as s:
        before = s.get(Opportunity, q.id).last_activity_at
        r1 = wr.create_weekly_actions(s, now=now)
        assert r1["created"] >= 1
        # the apply action exists, open, correct kind/title
        act = s.exec(
            __import__("sqlmodel").select(Action).where(Action.opportunity_id == q.id)
        ).first()
        assert act.kind == ActionKind.apply and act.status == ActionStatus.open
        assert act.title.startswith("Apply:")
        # last_activity_at not bumped
        assert s.get(Opportunity, q.id).last_activity_at == before
    with Session(engine) as s:
        r2 = wr.create_weekly_actions(s, now=now)  # idempotent
        apply_actions = s.exec(
            __import__("sqlmodel").select(Action).where(
                Action.opportunity_id == q.id, Action.kind == ActionKind.apply
            )
        ).all()
        assert len(apply_actions) == 1
