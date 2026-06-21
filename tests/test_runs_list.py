from sqlmodel import Session
from app.db import engine
from app.models import Run, RunStatus


def test_runs_list_returns_recent(client):
    with Session(engine) as s:
        s.add(Run(prompt="discover jobs", status=RunStatus.completed))
        s.add(Run(prompt="tailor cv", status=RunStatus.running))
        s.commit()
    r = client.get("/api/runs?limit=10")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 2
    assert {"id", "prompt", "status", "created_at"} <= set(rows[0].keys())
