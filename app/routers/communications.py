"""Communications endpoints — read path; writes go through the agent tool."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import services
from app.db import get_session
from app.models import Communication

router = APIRouter(prefix="/api/communications", tags=["communications"])


@router.get("")
def list_communications(
    opportunity_id: str | None = None,
    session: Session = Depends(get_session),
) -> list[Communication]:
    return services.list_communications(session, opportunity_id=opportunity_id)
