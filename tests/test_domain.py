"""Service layer + orchestration tests (no API key needed)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app import services
from app.db import engine
from app.models import (
    Action,
    ActionKind,
    ArtifactKind,
    CommChannel,
    CommDirection,
    Communication,
    Decision,
    DecisionKind,
    Opportunity,
    OpportunityType,
    PipelineStage,
)
from app.orchestration import board_columns, needs_attention, next_stage


def _naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_upsert_is_idempotent_and_merges_details():
    with Session(engine) as s:
        a = services.upsert_opportunity(
            s,
            type=OpportunityType.job,
            title="Staff Eng @ Acme",
            dedupe_key="acme-staff-eng",
            details={"salary": "200k"},
        )
        b = services.upsert_opportunity(
            s,
            type=OpportunityType.job,
            title="Staff Eng @ Acme",
            dedupe_key="acme-staff-eng",
            organization="Acme",
            details={"seniority": "staff"},
        )
        assert a.id == b.id  # no duplicate row
        assert b.organization == "Acme"
        assert b.details == {"salary": "200k", "seniority": "staff"}  # merged

        count = len(
            s.exec(
                select(Opportunity).where(Opportunity.dedupe_key == "acme-staff-eng")
            ).all()
        )
        assert count == 1


def test_set_stage_logs_a_decision():
    with Session(engine) as s:
        opp = services.upsert_opportunity(
            s, type=OpportunityType.business, title="RFP: City data platform"
        )
        services.set_stage(s, opp, PipelineStage.qualifying, rationale="looks viable")
        refreshed = s.get(Opportunity, opp.id)
        assert refreshed.stage == PipelineStage.qualifying
        decisions = s.exec(
            select(Decision).where(Decision.opportunity_id == opp.id)
        ).all()
        assert any(
            d.kind == DecisionKind.stage_change and "qualifying" in d.summary
            for d in decisions
        )


def test_action_lifecycle_touches_opportunity():
    with Session(engine) as s:
        opp = services.upsert_opportunity(
            s, type=OpportunityType.job, title="Apply test"
        )
        before = opp.last_activity_at
        action = services.add_action(
            s, title="Send follow-up", opportunity_id=opp.id, kind=ActionKind.followup
        )
        assert action.id is not None
        done = services.complete_action(s, action.id)
        assert done.status.value == "done" and done.completed_at is not None
        assert s.get(Opportunity, opp.id).last_activity_at >= before


def test_artifact_versioning():
    with Session(engine) as s:
        opp = services.upsert_opportunity(
            s, type=OpportunityType.job, title="CV target"
        )
        v1 = services.add_artifact(
            s, title="Tailored CV", body="v1", opportunity_id=opp.id, kind=ArtifactKind.cv
        )
        v2 = services.add_artifact(
            s, title="Tailored CV", body="v2", opportunity_id=opp.id, kind=ArtifactKind.cv
        )
        assert v1.version == 1 and v2.version == 2


def test_next_stage_and_board():
    assert next_stage(PipelineStage.new) == PipelineStage.qualifying
    assert next_stage(PipelineStage.in_dialogue) == PipelineStage.in_dialogue  # caps
    cols = board_columns()
    assert cols[0] == "new" and "won" in cols


def test_needs_attention_surfaces_the_right_items():
    old = _naive_now() - timedelta(days=30)
    with Session(engine) as s:
        # stale in-flight opportunity
        stale = Opportunity(
            type=OpportunityType.job,
            title="ATTN stale",
            stage=PipelineStage.active,
            last_activity_at=old,
            created_at=old,
        )
        # untriaged old opportunity
        untriaged = Opportunity(
            type=OpportunityType.business,
            title="ATTN untriaged",
            stage=PipelineStage.new,
            created_at=old,
            last_activity_at=old,
        )
        # fresh active opportunity that must NOT surface
        fresh = Opportunity(
            type=OpportunityType.job, title="ATTN fresh", stage=PipelineStage.active
        )
        s.add(stale)
        s.add(untriaged)
        s.add(fresh)
        s.commit()
        s.refresh(stale)
        s.refresh(untriaged)
        s.refresh(fresh)
        # overdue action
        s.add(
            Action(
                title="ATTN overdue",
                opportunity_id=stale.id,
                due_at=_naive_now() - timedelta(days=2),
            )
        )
        s.commit()

        result = needs_attention(s)
        ids = {i.get("opportunity_id") for i in result["items"]}
        kinds = {(i["kind"], i.get("opportunity_id"), i.get("title")) for i in result["items"]}

        assert stale.id in ids
        assert untriaged.id in ids
        assert fresh.id not in ids
        assert any(k[0] == "overdue_action" for k in kinds)
        assert result["counts"]["overdue_actions"] >= 1


def test_needs_attention_surfaces_overdue_followup():
    from datetime import timedelta

    from sqlmodel import Session

    from app.db import engine
    from app.models import Opportunity, OpportunityType
    from app.orchestration import needs_attention

    now_past = _naive_now() - timedelta(days=1)
    now_future = _naive_now() + timedelta(days=1)
    with Session(engine) as s:
        o = Opportunity(type=OpportunityType.job, title="ATTN comm")
        s.add(o)
        s.commit()
        s.refresh(o)
        s.add(Communication(direction=CommDirection.outbound, channel=CommChannel.email,
                            opportunity_id=o.id, subject="ping", follow_up_due_at=now_past))
        s.add(Communication(direction=CommDirection.outbound, channel=CommChannel.email,
                            opportunity_id=o.id, subject="future", follow_up_due_at=now_future))
        s.add(Communication(direction=CommDirection.inbound, channel=CommChannel.email,
                            opportunity_id=o.id, subject="none"))  # no follow-up
        s.commit()

        result = needs_attention(s)
        kinds = [i["kind"] for i in result["items"]]
        assert kinds.count("overdue_followup") == 1
        assert result["counts"]["overdue_followups"] == 1
        item = next(i for i in result["items"] if i["kind"] == "overdue_followup")
        assert item["opportunity_id"] == o.id and item["title"] == "ping"
