"""Opportunities + pipeline board endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app import briefing_service, services
from app.db import get_session
from app.models import (
    Action,
    Artifact,
    Briefing,
    Company,
    Decision,
    JobSource,
    Opportunity,
    OpportunityType,
    PipelineStage,
)
from app.orchestration import board_columns

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


class OpportunityCreate(BaseModel):
    type: OpportunityType
    title: str
    organization: str | None = None
    url: str | None = None
    location: str | None = None
    summary: str | None = None
    source: str | None = None
    dedupe_key: str | None = None
    fit_score: float | None = None
    details: dict[str, Any] = {}


class StageUpdate(BaseModel):
    stage: PipelineStage
    rationale: str = ""


@router.get("")
def list_opportunities(
    type: OpportunityType | None = None,
    stage: PipelineStage | None = None,
    include_archived: bool = False,
    session: Session = Depends(get_session),
) -> list[Opportunity]:
    return services.list_opportunities(
        session, type=type, stage=stage, include_archived=include_archived
    )


@router.post("")
def create_opportunity(
    body: OpportunityCreate, session: Session = Depends(get_session)
) -> Opportunity:
    return services.upsert_opportunity(
        session,
        type=body.type,
        title=body.title,
        dedupe_key=body.dedupe_key,
        organization=body.organization,
        url=body.url,
        location=body.location,
        summary=body.summary,
        source=body.source or "manual",
        fit_score=body.fit_score,
        details=body.details,
    )


@router.get("/{opp_id}")
def get_opportunity(opp_id: str, session: Session = Depends(get_session)) -> dict:
    opp = services.get_opportunity(session, opp_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    return {
        "opportunity": opp,
        "actions": services.list_actions(session, opportunity_id=opp_id),
        "artifacts": session.exec(
            select(Artifact)
            .where(Artifact.opportunity_id == opp_id)
            .order_by(Artifact.created_at.desc())
        ).all(),
        "decisions": session.exec(
            select(Decision)
            .where(Decision.opportunity_id == opp_id)
            .order_by(Decision.created_at.desc())
        ).all(),
        "applications": services.list_applications(session, opportunity_id=opp_id),
        "communications": services.list_communications(session, opportunity_id=opp_id),
        "contacts": services.list_contacts(session, opportunity_id=opp_id),
        "company": session.get(Company, opp.company_id) if opp.company_id else None,
        "source": session.get(JobSource, opp.source_id) if opp.source_id else None,
        "briefing": briefing_service.get_briefing(session, opp_id),
    }


@router.post("/{opp_id}/briefing/synthesize", response_model=Briefing)
async def synthesize_briefing_endpoint(
    opp_id: str, session: Session = Depends(get_session)
) -> Briefing:
    try:
        return await briefing_service.synthesize_briefing(session, opportunity_id=opp_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{opp_id}/briefing", response_model=Briefing | None)
def get_briefing_endpoint(
    opp_id: str, session: Session = Depends(get_session)
) -> Briefing | None:
    return briefing_service.get_briefing(session, opp_id)


@router.patch("/{opp_id}/stage")
def update_stage(
    opp_id: str, body: StageUpdate, session: Session = Depends(get_session)
) -> Opportunity:
    opp = services.get_opportunity(session, opp_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    return services.set_stage(session, opp, body.stage, rationale=body.rationale)


@router.post("/{opp_id}/archive")
def archive_opportunity(opp_id: str, session: Session = Depends(get_session)) -> Opportunity:
    opp = services.get_opportunity(session, opp_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    opp.archived = True
    session.add(opp)
    session.commit()
    session.refresh(opp)
    return opp


# --- Pipeline board ------------------------------------------------------- #

board_router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@board_router.get("")
def get_board(
    type: OpportunityType | None = None, session: Session = Depends(get_session)
) -> dict:
    opps = services.list_opportunities(session, type=type)
    by_stage: dict[str, list[Opportunity]] = {c: [] for c in board_columns()}
    for o in opps:
        by_stage.setdefault(o.stage.value, []).append(o)
    return {"columns": board_columns(), "by_stage": by_stage}
