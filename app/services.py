"""Domain service layer.

Single source of truth for mutating the system of record. Both the HTTP routers
and the agent's in-process MCP write-back tools call these, so a row created via
chat and a row created via the UI go through identical logic (dedupe, activity
touch, stage-change logging, artifact versioning).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import (
    Action,
    ActionKind,
    ActionStatus,
    Artifact,
    ArtifactFormat,
    ArtifactKind,
    Decision,
    DecisionKind,
    Opportunity,
    OpportunityType,
    PipelineStage,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC (see models._utcnow)


# --- Opportunities -------------------------------------------------------- #


def get_opportunity(session: Session, opp_id: str) -> Opportunity | None:
    return session.get(Opportunity, opp_id)


def list_opportunities(
    session: Session,
    *,
    type: OpportunityType | None = None,
    stage: PipelineStage | None = None,
    include_archived: bool = False,
) -> list[Opportunity]:
    stmt = select(Opportunity)
    if not include_archived:
        stmt = stmt.where(Opportunity.archived == False)  # noqa: E712
    if type is not None:
        stmt = stmt.where(Opportunity.type == type)
    if stage is not None:
        stmt = stmt.where(Opportunity.stage == stage)
    return list(session.exec(stmt.order_by(Opportunity.last_activity_at.desc())).all())


def upsert_opportunity(
    session: Session,
    *,
    type: OpportunityType,
    title: str,
    dedupe_key: str | None = None,
    organization: str | None = None,
    source: str | None = None,
    url: str | None = None,
    location: str | None = None,
    summary: str | None = None,
    fit_score: float | None = None,
    details: dict[str, Any] | None = None,
) -> Opportunity:
    """Create, or idempotently update when `dedupe_key` matches an existing row.

    On update, only provided (non-None) fields overwrite; `details` is merged.
    """
    existing: Opportunity | None = None
    if dedupe_key:
        existing = session.exec(
            select(Opportunity).where(Opportunity.dedupe_key == dedupe_key)
        ).first()

    if existing is None:
        opp = Opportunity(
            type=type,
            title=title,
            dedupe_key=dedupe_key,
            organization=organization,
            source=source,
            url=url,
            location=location,
            summary=summary,
            fit_score=fit_score,
            details=details or {},
        )
    else:
        opp = existing
        opp.title = title or opp.title
        for field, value in (
            ("organization", organization),
            ("source", source),
            ("url", url),
            ("location", location),
            ("summary", summary),
            ("fit_score", fit_score),
        ):
            if value is not None:
                setattr(opp, field, value)
        if details:
            opp.details = {**(opp.details or {}), **details}
        opp.updated_at = _utcnow()

    opp.last_activity_at = _utcnow()
    session.add(opp)
    session.commit()
    session.refresh(opp)
    return opp


def touch_opportunity(session: Session, opp: Opportunity) -> None:
    opp.last_activity_at = _utcnow()
    opp.updated_at = _utcnow()
    session.add(opp)
    session.commit()


def set_stage(
    session: Session,
    opp: Opportunity,
    new_stage: PipelineStage,
    *,
    rationale: str = "",
) -> Opportunity:
    """Move an opportunity to a stage and log the change as a Decision."""
    old = opp.stage
    if old == new_stage:
        return opp
    opp.stage = new_stage
    opp.updated_at = _utcnow()
    opp.last_activity_at = _utcnow()
    session.add(opp)
    session.add(
        Decision(
            opportunity_id=opp.id,
            kind=DecisionKind.stage_change,
            summary=f"{old.value} -> {new_stage.value}",
            rationale=rationale,
        )
    )
    session.commit()
    session.refresh(opp)
    return opp


# --- Actions -------------------------------------------------------------- #


def add_action(
    session: Session,
    *,
    title: str,
    opportunity_id: str | None = None,
    kind: ActionKind = ActionKind.other,
    detail: str = "",
    due_at: datetime | None = None,
) -> Action:
    action = Action(
        title=title,
        opportunity_id=opportunity_id,
        kind=kind,
        detail=detail,
        due_at=due_at,
    )
    session.add(action)
    if opportunity_id:
        opp = session.get(Opportunity, opportunity_id)
        if opp:
            opp.last_activity_at = _utcnow()
            session.add(opp)
    session.commit()
    session.refresh(action)
    return action


def complete_action(session: Session, action_id: int) -> Action | None:
    action = session.get(Action, action_id)
    if action is None:
        return None
    action.status = ActionStatus.done
    action.completed_at = _utcnow()
    action.updated_at = _utcnow()
    session.add(action)
    session.commit()
    session.refresh(action)
    return action


def list_actions(
    session: Session,
    *,
    status: ActionStatus | None = None,
    opportunity_id: str | None = None,
) -> list[Action]:
    stmt = select(Action)
    if status is not None:
        stmt = stmt.where(Action.status == status)
    if opportunity_id is not None:
        stmt = stmt.where(Action.opportunity_id == opportunity_id)
    return list(session.exec(stmt.order_by(Action.created_at.desc())).all())


# --- Artifacts ------------------------------------------------------------ #


def add_artifact(
    session: Session,
    *,
    title: str,
    body: str = "",
    opportunity_id: str | None = None,
    kind: ArtifactKind = ArtifactKind.other,
    format: ArtifactFormat = ArtifactFormat.markdown,
    provenance: str | None = None,
    file_path: str | None = None,
    run_id: str | None = None,
) -> Artifact:
    """Save an artifact, auto-incrementing version for same opp+kind+title."""
    prior = session.exec(
        select(Artifact)
        .where(
            Artifact.opportunity_id == opportunity_id,
            Artifact.kind == kind,
            Artifact.title == title,
        )
        .order_by(Artifact.version.desc())
    ).first()
    version = (prior.version + 1) if prior else 1

    artifact = Artifact(
        title=title,
        body=body,
        opportunity_id=opportunity_id,
        kind=kind,
        format=format,
        provenance=provenance,
        file_path=file_path,
        run_id=run_id,
        version=version,
    )
    session.add(artifact)
    if opportunity_id:
        opp = session.get(Opportunity, opportunity_id)
        if opp:
            opp.last_activity_at = _utcnow()
            session.add(opp)
    session.commit()
    session.refresh(artifact)
    return artifact


# --- Decisions ------------------------------------------------------------ #


def record_decision(
    session: Session,
    *,
    summary: str,
    opportunity_id: str | None = None,
    kind: DecisionKind = DecisionKind.note,
    rationale: str = "",
) -> Decision:
    decision = Decision(
        opportunity_id=opportunity_id,
        kind=kind,
        summary=summary,
        rationale=rationale,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision
