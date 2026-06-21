"""Interview calendar endpoints — CRUD + .ics export."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlmodel import Session

from app import services
from app.db import get_session
from app.ics import to_ics
from app.models import InterviewEvent, InterviewKind

router = APIRouter(prefix="/api/interviews", tags=["interviews"])


class InterviewCreate(BaseModel):
    title: str
    starts_at: datetime
    opportunity_id: str | None = None
    kind: InterviewKind = InterviewKind.other
    ends_at: datetime | None = None
    location: str = ""
    notes: str = ""


def _naive(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=None) if dt else None


def _ics_response(events: list[InterviewEvent], filename: str) -> Response:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return Response(
        content=to_ics(events, now=now),
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("")
def list_interviews(
    opportunity_id: str | None = None,
    upcoming: bool = False,
    session: Session = Depends(get_session),
) -> list[InterviewEvent]:
    return services.list_interviews(
        session, opportunity_id=opportunity_id, upcoming=upcoming
    )


@router.post("")
def create_interview(
    body: InterviewCreate, session: Session = Depends(get_session)
) -> InterviewEvent:
    return services.add_interview(
        session,
        title=body.title,
        starts_at=_naive(body.starts_at),
        opportunity_id=body.opportunity_id,
        kind=body.kind,
        ends_at=_naive(body.ends_at),
        location=body.location,
        notes=body.notes,
    )


@router.get("/calendar.ics")
def all_interviews_ics(session: Session = Depends(get_session)) -> Response:
    events = services.list_interviews(session, upcoming=True)
    return _ics_response(events, "interviews.ics")


@router.get("/{interview_id}.ics")
def interview_ics(
    interview_id: int, session: Session = Depends(get_session)
) -> Response:
    ev = session.get(InterviewEvent, interview_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="interview not found")
    return _ics_response([ev], f"interview-{interview_id}.ics")


@router.delete("/{interview_id}", status_code=204)
def delete_interview(
    interview_id: int, session: Session = Depends(get_session)
) -> Response:
    ev = session.get(InterviewEvent, interview_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="interview not found")
    gcal_id = ev.gcal_event_id
    if not services.delete_interview(session, interview_id):
        raise HTTPException(status_code=404, detail="interview not found")
    if gcal_id:
        from app import google_oauth as go, gcal_service
        from app.models import _utcnow
        try:
            if go.status(session).get("connected"):
                gcal_service.delete_event(go.get_access_token(session, now=_utcnow()), gcal_id)
        except Exception:  # noqa: BLE001 — google cleanup is best-effort
            pass
    return Response(status_code=204)
