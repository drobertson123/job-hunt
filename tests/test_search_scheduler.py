from datetime import datetime, timedelta

import pytest
from sqlmodel import Session

from app.db import engine
from app import services
from app.models import JobSourceKind
from app import search_scheduler as sched


def _src(**kw):
    with Session(engine) as s:
        return services.upsert_job_source(s, **kw)


def test_build_search_prompt_includes_query():
    p = sched.build_search_prompt("senior ML engineer remote")
    assert "senior ML engineer remote" in p
    assert "save_opportunity" in p


def test_due_job_sources_respects_optin_query_and_cutoff():
    now = datetime(2026, 6, 21, 12, 0)
    on = _src(name="On", kind=JobSourceKind.job_board, saved_query="ml jobs", auto_search=True)
    _src(name="Off", saved_query="ml jobs", auto_search=False)        # not opted in
    _src(name="NoQuery", auto_search=True)                            # no saved_query
    recent = _src(name="Recent", saved_query="x", auto_search=True)
    with Session(engine) as s:
        row = s.get(type(recent), recent.id)
        row.last_checked_at = now - timedelta(hours=1)               # checked recently
        s.add(row); s.commit()
        due = sched.due_job_sources(s, now=now, interval_hours=24)
    ids = {d.id for d in due}
    assert on.id in ids
    assert recent.id not in ids
    assert len(ids) == 1


@pytest.mark.asyncio
async def test_run_source_search_stamps_and_uses_query():
    now = datetime(2026, 6, 21, 12, 0)
    src = _src(name="Run", saved_query="data eng roles", auto_search=True)
    captured = {}

    async def fake_runner(prompt, **kw):
        captured["prompt"] = prompt
        if False:
            yield  # make this an async generator

    res = await sched.run_source_search(src.id, runner=fake_runner, now=now)
    assert res["status"] == "ran"
    assert "data eng roles" in captured["prompt"]
    with Session(engine) as s:
        row = s.get(type(src), src.id)
        assert row.last_checked_at == now


@pytest.mark.asyncio
async def test_run_due_searches_runs_only_due(monkeypatch):
    now = datetime(2026, 6, 21, 12, 0)
    due = _src(name="Due", saved_query="q1", auto_search=True)
    _src(name="Skip", saved_query="q2", auto_search=False)
    ran = []

    async def fake_runner(prompt, **kw):
        ran.append(prompt)
        if False:
            yield

    results = await sched.run_due_searches(now=now, runner=fake_runner)
    assert len(ran) == 1
    assert any(r["source_id"] == due.id and r["status"] == "ran" for r in results)


@pytest.mark.asyncio
async def test_scheduler_start_idempotent_and_stop():
    s = sched.DailySearchScheduler()
    await s.start(poll_seconds=3600)
    first = s._task
    await s.start(poll_seconds=3600)   # idempotent
    assert s._task is first
    await s.stop()
    assert s._task is None
