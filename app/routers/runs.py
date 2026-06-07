"""Runs endpoint — fetch a run and replay its events (re-attach after a drop)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.agent.runner import events_after
from app.db import get_session
from app.models import Run

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_session)) -> Run:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.get("/{run_id}/events")
def get_run_events(run_id: str, after_seq: int = -1) -> list[dict]:
    """Events with seq > after_seq, in order — clients resume from their last seq."""
    return events_after(run_id, after_seq)
