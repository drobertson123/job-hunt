"""Health endpoint — proves the API + DB round-trip and reports agent readiness."""

from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends
from sqlmodel import Session, func, select

from app import __version__
from app.db import get_session
from app.models import Note, Run
from app.settings_service import resolve_anthropic_key

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict:
    # A real DB read so this endpoint proves the SQLite round-trip.
    note_count = session.exec(select(func.count()).select_from(Note)).one()
    run_count = session.exec(select(func.count()).select_from(Run)).one()
    return {
        "status": "ok",
        "version": __version__,
        "db": {"notes": note_count, "runs": run_count},
        "agent": {
            "claude_cli": shutil.which("claude"),
            "anthropic_key_configured": bool(resolve_anthropic_key(session)),
        },
    }
