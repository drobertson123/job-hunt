"""Relationships / network endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import relationships_service
from app.db import get_session

router = APIRouter(prefix="/api/relationships", tags=["relationships"])


@router.get("")
def get_relationships(session: Session = Depends(get_session)) -> dict:
    return relationships_service.compute_relationships(session)
