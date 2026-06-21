from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import Action, ActionStatus


def _action(s: Session) -> Action:
    a = Action(title="Task")
    s.add(a)
    s.commit()
    s.refresh(a)
    return a


def test_snooze_action():
    with Session(engine) as s:
        a = _action(s)
        out = services.snooze_action(s, a.id)
        assert out is not None and out.status == ActionStatus.snoozed


def test_reopen_action_clears_completed():
    with Session(engine) as s:
        a = _action(s)
        services.complete_action(s, a.id)
        out = services.reopen_action(s, a.id)
        assert out is not None and out.status == ActionStatus.open
        assert out.completed_at is None


def test_snooze_reopen_missing_returns_none():
    with Session(engine) as s:
        assert services.snooze_action(s, 999999) is None
        assert services.reopen_action(s, 999999) is None
