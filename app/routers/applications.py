"""Applications endpoints — read path; writes go through the agent tool."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import services
from app.db import get_session
from app.models import Application

router = APIRouter(prefix="/api/applications", tags=["applications"])


@router.get("")
def list_applications(
    opportunity_id: str | None = None,
    session: Session = Depends(get_session),
) -> list[Application]:
    return services.list_applications(session, opportunity_id=opportunity_id)
