"""Job-source endpoints — list, create, update (opt-in), and run a search now."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app import services
from app.db import get_session
from app.models import JobSource, JobSourceKind
from app.search_scheduler import run_source_search

router = APIRouter(prefix="/api/job-sources", tags=["job-sources"])


class JobSourceCreate(BaseModel):
    name: str
    kind: JobSourceKind = JobSourceKind.other
    url: str | None = None
    saved_query: str | None = None
    auto_search: bool = False
    notes: str | None = None


class JobSourceUpdate(BaseModel):
    name: str | None = None
    kind: JobSourceKind | None = None
    url: str | None = None
    saved_query: str | None = None
    auto_search: bool | None = None
    notes: str | None = None


@router.get("")
def list_job_sources(session: Session = Depends(get_session)) -> list[JobSource]:
    return services.list_job_sources(session)


@router.post("")
def create_job_source(
    body: JobSourceCreate, session: Session = Depends(get_session)
) -> JobSource:
    return services.upsert_job_source(
        session,
        name=body.name,
        kind=body.kind,
        url=body.url,
        saved_query=body.saved_query,
        auto_search=body.auto_search,
        notes=body.notes,
    )


@router.patch("/{source_id}")
def update_job_source(
    source_id: str, body: JobSourceUpdate, session: Session = Depends(get_session)
) -> JobSource:
    existing = session.get(JobSource, source_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="job source not found")
    return services.upsert_job_source(
        session,
        name=body.name if body.name is not None else existing.name,
        kind=body.kind,
        url=body.url,
        saved_query=body.saved_query,
        auto_search=body.auto_search,
        notes=body.notes,
        job_source_id=source_id,
    )


@router.post("/{source_id}/search")
async def search_now(
    source_id: str, session: Session = Depends(get_session)
) -> dict:
    if session.get(JobSource, source_id) is None:
        raise HTTPException(status_code=404, detail="job source not found")
    return await run_source_search(source_id)
