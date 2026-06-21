"""Domain service layer.

Single source of truth for mutating the system of record. Both the HTTP routers
and the agent's in-process MCP write-back tools call these, so a row created via
chat and a row created via the UI go through identical logic (dedupe, activity
touch, stage-change logging, artifact versioning).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import (
    Action,
    ActionKind,
    ActionStatus,
    Application,
    ApplicationStatus,
    Artifact,
    ArtifactFormat,
    ArtifactKind,
    CommChannel,
    CommDirection,
    Communication,
    Company,
    CompanySize,
    Contact,
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


# --- Applications ---------------------------------------------------------- #


def record_application(
    session: Session,
    *,
    opportunity_id: str,
    status: ApplicationStatus = ApplicationStatus.draft,
    company_id: str | None = None,
    portal_url: str | None = None,
    external_id: str | None = None,
    submitted_at: datetime | None = None,
    login_hint: str | None = None,
    notes: str = "",
    application_id: str | None = None,
) -> Application:
    app_row = session.get(Application, application_id) if application_id else None
    if app_row is None:
        app_row = Application(opportunity_id=opportunity_id)
    # ponytail: full overwrite from args — caller sends the intended state.
    app_row.opportunity_id = opportunity_id
    app_row.status = status
    app_row.company_id = company_id
    app_row.portal_url = portal_url
    app_row.external_id = external_id
    app_row.submitted_at = submitted_at
    app_row.login_hint = login_hint
    app_row.notes = notes
    app_row.updated_at = _utcnow()
    session.add(app_row)
    opp = session.get(Opportunity, opportunity_id)
    if opp:
        opp.last_activity_at = _utcnow()
        session.add(opp)
    session.commit()
    session.refresh(app_row)
    return app_row


def list_applications(
    session: Session, opportunity_id: str | None = None
) -> list[Application]:
    q = select(Application)
    if opportunity_id:
        q = q.where(Application.opportunity_id == opportunity_id)
    return list(session.exec(q.order_by(Application.created_at.desc())).all())


# --- Communications --------------------------------------------------------- #


def record_communication(
    session: Session,
    *,
    direction: CommDirection,
    channel: CommChannel,
    opportunity_id: str | None = None,
    contact_id: int | None = None,
    company_id: str | None = None,
    subject: str = "",
    body: str = "",
    occurred_at: datetime | None = None,
    thread_key: str | None = None,
    follow_up_due_at: datetime | None = None,
    communication_id: int | None = None,
) -> Communication:
    row = session.get(Communication, communication_id) if communication_id else None
    if row is None:
        row = Communication(direction=direction, channel=channel)
    # ponytail: overwrite from args (caller sends intended state); occurred_at is
    # guarded because the column is non-null with a model default.
    row.direction = direction
    row.channel = channel
    row.opportunity_id = opportunity_id
    row.contact_id = contact_id
    row.company_id = company_id
    row.subject = subject
    row.body = body
    if occurred_at is not None:
        row.occurred_at = occurred_at
    row.thread_key = thread_key
    row.follow_up_due_at = follow_up_due_at
    session.add(row)
    if opportunity_id:
        opp = session.get(Opportunity, opportunity_id)
        if opp:
            opp.last_activity_at = _utcnow()
            session.add(opp)
    session.commit()
    session.refresh(row)
    return row


def list_communications(
    session: Session, opportunity_id: str | None = None
) -> list[Communication]:
    q = select(Communication)
    if opportunity_id:
        q = q.where(Communication.opportunity_id == opportunity_id)
    return list(session.exec(q.order_by(Communication.occurred_at.desc())).all())


# --- Companies ------------------------------------------------------------ #


def upsert_company(
    session: Session,
    *,
    name: str,
    domain: str | None = None,
    industry: str | None = None,
    size: CompanySize | None = None,
    hq_location: str | None = None,
    careers_url: str | None = None,
    linkedin_url: str | None = None,
    ats_vendor: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
    company_id: str | None = None,
    link_opportunity_id: str | None = None,
) -> Company:
    row = session.get(Company, company_id) if company_id else None
    if row is None:
        row = session.exec(
            select(Company).where(func.lower(Company.name) == name.strip().lower())
        ).first()
    if row is None:
        row = Company(name=name.strip())
    # Incremental: only non-None args overwrite (mirrors upsert_opportunity).
    if domain is not None:
        row.domain = domain
    if industry is not None:
        row.industry = industry
    if size is not None:
        row.size = size
    if hq_location is not None:
        row.hq_location = hq_location
    if careers_url is not None:
        row.careers_url = careers_url
    if linkedin_url is not None:
        row.linkedin_url = linkedin_url
    if ats_vendor is not None:
        row.ats_vendor = ats_vendor
    if summary is not None:
        row.summary = summary
    if notes is not None:
        row.notes = notes
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    if link_opportunity_id:
        opp = session.get(Opportunity, link_opportunity_id)
        if opp is not None:
            opp.company_id = row.id
            session.add(opp)
            session.commit()
    return row


def list_companies(session: Session) -> list[Company]:
    return list(session.exec(select(Company).order_by(func.lower(Company.name))).all())


def backfill_company_ids(session: Session) -> dict[str, int]:
    opportunities_linked = 0
    for opp in session.exec(select(Opportunity)).all():
        if opp.organization and opp.organization.strip() and opp.company_id is None:
            c = upsert_company(session, name=opp.organization)
            opp.company_id = c.id
            session.add(opp)
            opportunities_linked += 1
    contacts_linked = 0
    for ct in session.exec(select(Contact)).all():
        if ct.organization and ct.organization.strip() and ct.company_id is None:
            c = upsert_company(session, name=ct.organization)
            ct.company_id = c.id
            session.add(ct)
            contacts_linked += 1
    session.commit()
    total = len(session.exec(select(Company)).all())
    return {
        "opportunities_linked": opportunities_linked,
        "contacts_linked": contacts_linked,
        "companies": total,
    }


# --- Contacts ------------------------------------------------------------ #


def add_contact(
    session: Session,
    *,
    name: str,
    opportunity_id: str | None = None,
    role: str | None = None,
    organization: str | None = None,
    company_id: str | None = None,
    link: str | None = None,
    notes: str = "",
    contact_id: int | None = None,
) -> Contact:
    row = session.get(Contact, contact_id) if contact_id else None
    if row is None:
        row = Contact(name=name)
    # ponytail: overwrite from args (caller sends intended state).
    row.name = name
    row.opportunity_id = opportunity_id
    row.role = role
    row.organization = organization
    row.company_id = company_id
    row.link = link
    row.notes = notes
    session.add(row)
    if opportunity_id:
        opp = session.get(Opportunity, opportunity_id)
        if opp:
            opp.last_activity_at = _utcnow()
            session.add(opp)
    session.commit()
    session.refresh(row)
    return row


def list_contacts(
    session: Session, opportunity_id: str | None = None
) -> list[Contact]:
    q = select(Contact)
    if opportunity_id:
        q = q.where(Contact.opportunity_id == opportunity_id)
    return list(session.exec(q.order_by(Contact.created_at.desc())).all())
