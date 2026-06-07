"""Orchestration — pipeline helpers + the "what needs attention" engine.

This is seam #2 in practice: the DB is the memory, and *app logic* (not a
long-lived agent) proactively surfaces what's stale or due so nothing gets
dropped. An agent session is invoked only when the user acts on an item.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import Session, select

from app.config import get_config
from app.models import (
    STAGE_ORDER,
    Action,
    ActionStatus,
    Opportunity,
    PipelineStage,
)

# Stages a linear "advance" walks through; won/lost are set explicitly.
_ADVANCEABLE = [
    PipelineStage.new,
    PipelineStage.qualifying,
    PipelineStage.analyzing,
    PipelineStage.active,
    PipelineStage.in_dialogue,
]

# Stages considered "in flight" for staleness detection.
ACTIVE_STAGES = [PipelineStage.active, PipelineStage.in_dialogue]
UNTRIAGED_STAGES = [PipelineStage.new, PipelineStage.qualifying]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC (see models._utcnow)


def board_columns() -> list[str]:
    """Stage values in order, for rendering the pipeline board."""
    return [s.value for s in STAGE_ORDER]


def next_stage(stage: PipelineStage) -> PipelineStage:
    """The next stage in a linear advance (stops at in_dialogue)."""
    if stage in _ADVANCEABLE:
        i = _ADVANCEABLE.index(stage)
        if i + 1 < len(_ADVANCEABLE):
            return _ADVANCEABLE[i + 1]
    return stage


def needs_attention(session: Session) -> dict[str, Any]:
    """Surface overdue actions, stale in-flight opportunities, and untriaged ones."""
    cfg = get_config()
    now = _utcnow()
    stale_cutoff = now - timedelta(days=cfg.attention_stale_active_days)
    untriaged_cutoff = now - timedelta(days=cfg.attention_untriaged_days)

    items: list[dict[str, Any]] = []

    overdue = session.exec(
        select(Action).where(
            Action.status == ActionStatus.open,
            Action.due_at.is_not(None),
            Action.due_at < now,
        )
    ).all()
    for a in overdue:
        items.append(
            {
                "kind": "overdue_action",
                "severity": "high",
                "action_id": a.id,
                "opportunity_id": a.opportunity_id,
                "title": a.title,
                "due_at": a.due_at.isoformat() if a.due_at else None,
                "reason": "Action is overdue",
            }
        )

    stale = session.exec(
        select(Opportunity).where(
            Opportunity.archived == False,  # noqa: E712
            Opportunity.stage.in_(ACTIVE_STAGES),
            Opportunity.last_activity_at < stale_cutoff,
        )
    ).all()
    for o in stale:
        items.append(
            {
                "kind": "stale_opportunity",
                "severity": "medium",
                "opportunity_id": o.id,
                "title": o.title,
                "stage": o.stage.value,
                "last_activity_at": o.last_activity_at.isoformat(),
                "reason": f"No activity in {cfg.attention_stale_active_days}+ days",
            }
        )

    untriaged = session.exec(
        select(Opportunity).where(
            Opportunity.archived == False,  # noqa: E712
            Opportunity.stage.in_(UNTRIAGED_STAGES),
            Opportunity.created_at < untriaged_cutoff,
        )
    ).all()
    for o in untriaged:
        items.append(
            {
                "kind": "untriaged_opportunity",
                "severity": "low",
                "opportunity_id": o.id,
                "title": o.title,
                "stage": o.stage.value,
                "created_at": o.created_at.isoformat(),
                "reason": f"Untriaged for {cfg.attention_untriaged_days}+ days",
            }
        )

    return {
        "items": items,
        "counts": {
            "overdue_actions": len(overdue),
            "stale_opportunities": len(stale),
            "untriaged_opportunities": len(untriaged),
            "total": len(items),
        },
    }
