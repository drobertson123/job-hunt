"""'What needs attention' endpoint — app logic over the DB (seam #2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.orchestration import needs_attention

router = APIRouter(prefix="/api/attention", tags=["attention"])


@router.get("")
def get_attention(session: Session = Depends(get_session)) -> dict:
    return needs_attention(session)
