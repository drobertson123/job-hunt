"""Notes endpoint — the canvas reads saved notes (the write-back-seam output)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db import get_session
from app.models import Note

router = APIRouter(prefix="/api/notes", tags=["notes"])


@router.get("")
def list_notes(
    run_id: str | None = None,
    session: Session = Depends(get_session),
) -> list[Note]:
    stmt = select(Note).order_by(Note.id.desc())
    if run_id:
        stmt = stmt.where(Note.run_id == run_id)
    return session.exec(stmt).all()
