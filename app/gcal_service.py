"""Push interview events to Google Calendar (injectable HTTP for tests)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

import httpx
from sqlmodel import Session, select

from app.models import InterviewEvent, _utcnow

EVENTS_URI = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

Request = Callable[..., dict[str, Any]]


def _request(method: str, url: str, access_token: str, *, json: Any = None, params: Any = None) -> dict[str, Any]:
    r = httpx.request(method, url, headers={"Authorization": f"Bearer {access_token}"}, json=json, params=params, timeout=30)
    r.raise_for_status()
    return r.json() if r.content else {}


def event_body(iv: InterviewEvent) -> dict[str, Any]:
    end = iv.ends_at or (iv.starts_at + timedelta(hours=1))
    body: dict[str, Any] = {
        "summary": iv.title,
        "start": {"dateTime": iv.starts_at.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
    }
    if iv.location:
        body["location"] = iv.location
    if iv.notes:
        body["description"] = iv.notes
    return body


def push_interview(session: Session, iv: InterviewEvent, *, access_token: str, request: Request = _request) -> str | None:
    body = event_body(iv)
    if iv.gcal_event_id:
        request("PATCH", f"{EVENTS_URI}/{iv.gcal_event_id}", access_token, json=body)
        return iv.gcal_event_id
    resp = request("POST", EVENTS_URI, access_token, json=body)
    iv.gcal_event_id = resp.get("id")
    session.add(iv)
    session.commit()
    session.refresh(iv)
    return iv.gcal_event_id


def delete_event(access_token: str, event_id: str, *, request: Request = _request) -> None:
    try:
        request("DELETE", f"{EVENTS_URI}/{event_id}", access_token)
    except Exception:  # noqa: BLE001 — already-deleted is fine
        pass


def sync_upcoming(session: Session, *, access_token: str, request: Request = _request, now: datetime | None = None) -> dict[str, int]:
    now = now or _utcnow()
    rows = session.exec(select(InterviewEvent).where(InterviewEvent.starts_at >= now)).all()
    pushed = updated = 0
    for iv in rows:
        had = bool(iv.gcal_event_id)
        push_interview(session, iv, access_token=access_token, request=request)
        if had:
            updated += 1
        else:
            pushed += 1
    return {"pushed": pushed, "updated": updated}
