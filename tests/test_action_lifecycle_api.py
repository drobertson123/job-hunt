from __future__ import annotations

from sqlmodel import Session

from app.db import engine
from app.models import Action


def _action_id() -> int:
    with Session(engine) as s:
        a = Action(title="Task")
        s.add(a)
        s.commit()
        s.refresh(a)
        return a.id


def test_snooze_then_reopen_endpoints(client):
    aid = _action_id()
    sn = client.post(f"/api/actions/{aid}/snooze")
    assert sn.status_code == 200 and sn.json()["status"] == "snoozed"
    ro = client.post(f"/api/actions/{aid}/reopen")
    assert ro.status_code == 200 and ro.json()["status"] == "open"


def test_snooze_missing_404(client):
    assert client.post("/api/actions/999999/snooze").status_code == 404
