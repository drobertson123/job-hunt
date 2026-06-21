"""Actions endpoints (next steps / tasks that power 'what needs attention')."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app import services
from app.db import get_session
from app.models import Action, ActionKind, ActionStatus

router = APIRouter(prefix="/api/actions", tags=["actions"])


class ActionCreate(BaseModel):
    title: str
    opportunity_id: str | None = None
    kind: ActionKind = ActionKind.other
    detail: str = ""
    due_at: datetime | None = None


@router.get("")
def list_actions(
    status: ActionStatus | None = None,
    opportunity_id: str | None = None,
    session: Session = Depends(get_session),
) -> list[Action]:
    return services.list_actions(session, status=status, opportunity_id=opportunity_id)


@router.post("")
def create_action(body: ActionCreate, session: Session = Depends(get_session)) -> Action:
    return services.add_action(
        session,
        title=body.title,
        opportunity_id=body.opportunity_id,
        kind=body.kind,
        detail=body.detail,
        due_at=body.due_at.replace(tzinfo=None) if body.due_at else None,
    )


@router.post("/{action_id}/complete")
def complete_action(action_id: int, session: Session = Depends(get_session)) -> Action:
    action = services.complete_action(session, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="action not found")
    return action


@router.post("/{action_id}/snooze")
def snooze_action(action_id: int, session: Session = Depends(get_session)) -> Action:
    action = services.snooze_action(session, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="action not found")
    return action


@router.post("/{action_id}/reopen")
def reopen_action(action_id: int, session: Session = Depends(get_session)) -> Action:
    action = services.reopen_action(session, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="action not found")
    return action
