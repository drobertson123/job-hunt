"""Companies endpoints — read + backfill; enrichment goes through the agent tool."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import services
from app.db import get_session
from app.models import Company

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("")
def list_companies(session: Session = Depends(get_session)) -> list[Company]:
    return services.list_companies(session)


@router.post("/backfill")
def backfill(session: Session = Depends(get_session)) -> dict:
    return services.backfill_company_ids(session)
