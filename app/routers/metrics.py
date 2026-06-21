"""Pipeline metrics endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import metrics_service
from app.db import get_session

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("")
def get_metrics(session: Session = Depends(get_session)) -> dict:
    return metrics_service.compute_metrics(session)
