"""Weekly identify->apply->follow-up review endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import weekly_review
from app.db import get_session

router = APIRouter(prefix="/api/weekly-review", tags=["weekly-review"])


@router.get("")
def get_weekly_review(session: Session = Depends(get_session)) -> dict:
    return weekly_review.weekly_review(session)


@router.post("/actions")
def create_weekly_actions(session: Session = Depends(get_session)) -> dict:
    return weekly_review.create_weekly_actions(session)
