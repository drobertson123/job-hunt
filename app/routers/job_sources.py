"""Job-source endpoints — read path; attribution is written via the agent tool."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import services
from app.db import get_session
from app.models import JobSource

router = APIRouter(prefix="/api/job-sources", tags=["job-sources"])


@router.get("")
def list_job_sources(session: Session = Depends(get_session)) -> list[JobSource]:
    return services.list_job_sources(session)
