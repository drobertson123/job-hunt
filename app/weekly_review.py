"""Weekly identify -> apply -> follow-up review over the pipeline (deterministic)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from app.models import (
    Action,
    ActionKind,
    ActionStatus,
    Application,
    InterviewEvent,
    Opportunity,
    PipelineStage,
    _utcnow,
)

IDENTIFY_STAGES = [PipelineStage.new]
APPLY_STAGES = [PipelineStage.qualifying, PipelineStage.analyzing]
FOLLOWUP_STAGES = [PipelineStage.active, PipelineStage.in_dialogue]


def _brief(o: Opportunity) -> dict[str, Any]:
    return {
        "id": o.id,
        "title": o.title,
        "organization": o.organization,
        "stage": o.stage.value,
        "type": o.type.value,
    }


def weekly_review(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or _utcnow()
    week_end = now + timedelta(days=7)

    identify = session.exec(
        select(Opportunity)
        .where(Opportunity.stage.in_(IDENTIFY_STAGES))
        .order_by(Opportunity.created_at.desc())
    ).all()

    applied_ids = set(session.exec(select(Application.opportunity_id)).all())
    apply_rows = session.exec(
        select(Opportunity)
        .where(Opportunity.stage.in_(APPLY_STAGES))
        .order_by(Opportunity.created_at.desc())
    ).all()
    to_apply = [o for o in apply_rows if o.id not in applied_ids]

    follow = session.exec(
        select(Opportunity)
        .where(Opportunity.stage.in_(FOLLOWUP_STAGES))
        .order_by(Opportunity.last_activity_at)
    ).all()

    interviews = session.exec(
        select(InterviewEvent)
        .where(InterviewEvent.starts_at >= now, InterviewEvent.starts_at <= week_end)
        .order_by(InterviewEvent.starts_at)
    ).all()

    return {
        "to_identify": [_brief(o) for o in identify],
        "to_apply": [_brief(o) for o in to_apply],
        "to_follow_up": [_brief(o) for o in follow],
        "interviews_this_week": [
            {
                "id": i.id,
                "title": i.title,
                "starts_at": i.starts_at.isoformat(),
                "opportunity_id": i.opportunity_id,
            }
            for i in interviews
        ],
        "counts": {
            "to_identify": len(identify),
            "to_apply": len(to_apply),
            "to_follow_up": len(follow),
            "interviews_this_week": len(interviews),
        },
    }


def create_weekly_actions(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    plan = weekly_review(session, now=now)
    specs = [
        ("to_identify", ActionKind.research, "Triage"),
        ("to_apply", ActionKind.apply, "Apply"),
        ("to_follow_up", ActionKind.followup, "Follow up"),
    ]
    created = 0
    for bucket, kind, verb in specs:
        for item in plan[bucket]:
            oid = item["id"]
            existing = session.exec(
                select(Action).where(
                    Action.opportunity_id == oid,
                    Action.kind == kind,
                    Action.status == ActionStatus.open,
                )
            ).first()
            if existing is not None:
                continue
            session.add(
                Action(title=f"{verb}: {item['title']}", opportunity_id=oid, kind=kind)
            )
            created += 1
    session.commit()
    return {"created": created}
