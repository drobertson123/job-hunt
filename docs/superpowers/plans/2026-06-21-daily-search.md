# Automated Daily Job Searches Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An in-process daily scheduler that auto-runs job-discovery for opted-in saved queries, plus API/UI to configure and trigger them.

**Architecture:** `JobSource.auto_search` opt-in toggle; an `app/search_scheduler.py` background loop (started in lifespan) that runs each due source's `saved_query` through the agent (`stream_run` → WebSearch + `save_opportunity`, which dedups by URL), then stamps `last_checked_at`. Runner injectable for deterministic tests.

**Tech Stack:** Python 3.12, SQLModel/SQLite, FastAPI lifespan + asyncio, Next.js/React/Tailwind, pytest.

## Global Constraints
- Naive-UTC datetimes everywhere — use `from app.models import _utcnow` for "now" and stamping (matches the schema). Time comparisons take an injected `now` so tests are deterministic.
- No global enable flag: the per-source `auto_search` (default False) is the opt-in. The scheduler is started unconditionally but is inert until a source has `auto_search=True` and a non-empty `saved_query`.
- Discovery writes ONLY through `mcp__app__save_opportunity` (idempotent on `dedupe_key=url`); the scheduler never writes opportunities directly.
- pytest interpreter: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest …` (worktree has no local .venv). Frontend: `npm --prefix frontend install` then `npm --prefix frontend run build`.
- Verification: `bash scripts/ci/gate.sh` GREEN; `npm --prefix frontend run build` succeeds.
- Do NOT invoke any finishing/branch skill — stop after committing and reporting.

---

### Task 1: Model column, config, service param, and the scheduler

**Files:**
- Modify: `app/models.py` (add `auto_search` to `JobSource`)
- Modify: `app/db.py` (`_ensure_column` migration)
- Modify: `app/config.py` (two knobs)
- Modify: `app/services.py` (`upsert_job_source` gains `auto_search`)
- Create: `app/search_scheduler.py`
- Test: `tests/test_search_scheduler.py`

**Interfaces:**
- Produces: `build_search_prompt`, `due_job_sources`, `run_source_search`, `run_due_searches`, `DailySearchScheduler`, `get_scheduler` in `app/search_scheduler.py`.

- [ ] **Step 1: Add the model column + migration + config**

In `app/models.py`, in `class JobSource`, after `saved_query: ...`, add:
```python
    auto_search: bool = False  # opt in to the daily scheduler
```
In `app/db.py` `init_db`, after the existing `_ensure_column(...)` lines, add:
```python
    _ensure_column(engine, "job_sources", "auto_search", "BOOLEAN DEFAULT 0")
```
In `app/config.py`, after `agent_keep_alive_seconds`, add:
```python
    # Daily job-search scheduler.
    daily_search_interval_hours: int = 24
    daily_search_poll_seconds: int = 3600
```

- [ ] **Step 2: Extend `upsert_job_source` with `auto_search`**

In `app/services.py`, add a parameter `auto_search: bool | None = None` to `upsert_job_source`'s signature (place it after `saved_query`), and inside the incremental block add:
```python
    if auto_search is not None:
        row.auto_search = auto_search
```

- [ ] **Step 3: Write the failing scheduler test**

Create `tests/test_search_scheduler.py`:
```python
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
```

- [ ] **Step 4: Run it to verify it fails**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_search_scheduler.py -q`
Expected: FAIL (`ModuleNotFoundError: app.search_scheduler`).

- [ ] **Step 5: Implement `app/search_scheduler.py`**

```python
"""In-process daily job-search scheduler.

Inert until a JobSource is opted in (auto_search=True with a saved_query). For
each due source it runs the saved query through the agent (WebSearch +
save_opportunity, which dedups by URL), then stamps last_checked_at. Mirrors the
keep-alive background task; `runner` is injectable for deterministic tests.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Callable

from sqlmodel import Session, select

from app.agent.runner import stream_run
from app.config import get_config
from app.db import engine
from app.models import JobSource, _utcnow

logger = logging.getLogger(__name__)


def build_search_prompt(saved_query: str) -> str:
    return (
        "Search current job postings matching this saved query:\n"
        f"  {saved_query}\n\n"
        "Use WebSearch (and WebFetch to confirm promising hits) to find LIVE "
        "postings. For each genuinely new posting (at most 10), call "
        'mcp__app__save_opportunity with: type="job", title, organization, '
        "url (REQUIRED — the posting URL), summary (2-3 sentences), "
        'source="daily-search", and dedupe_key set to the posting URL. '
        "Never fabricate a posting or a URL; skip anything you cannot source. "
        "Reply with a one-line-per-find summary."
    )


def due_job_sources(
    session: Session, *, now: datetime, interval_hours: int
) -> list[JobSource]:
    cutoff = now - timedelta(hours=interval_hours)
    due: list[JobSource] = []
    for s in session.exec(select(JobSource)).all():
        if not s.auto_search or not (s.saved_query or "").strip():
            continue
        if s.last_checked_at is None or s.last_checked_at < cutoff:
            due.append(s)
    return due


async def run_source_search(
    source_id: str,
    *,
    runner: Callable[..., Any] = stream_run,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or _utcnow()
    with Session(engine) as s:
        src = s.get(JobSource, source_id)
        if src is None:
            return {"source_id": source_id, "status": "not_found"}
        query = (src.saved_query or "").strip()
    if not query:
        return {"source_id": source_id, "status": "skipped"}
    prompt = build_search_prompt(query)
    async for _ in runner(prompt):
        pass
    with Session(engine) as s:
        src = s.get(JobSource, source_id)
        if src is not None:
            src.last_checked_at = now
            s.add(src)
            s.commit()
    return {"source_id": source_id, "status": "ran"}


async def run_due_searches(
    *, now: datetime | None = None, runner: Callable[..., Any] = stream_run
) -> list[dict[str, Any]]:
    now = now or _utcnow()
    with Session(engine) as s:
        ids = [
            d.id
            for d in due_job_sources(
                s, now=now, interval_hours=get_config().daily_search_interval_hours
            )
        ]
    results: list[dict[str, Any]] = []
    for sid in ids:
        try:
            results.append(await run_source_search(sid, runner=runner, now=now))
        except Exception:  # noqa: BLE001 — one bad source must not stop the rest
            logger.warning("daily search failed for source %s", sid, exc_info=True)
            results.append({"source_id": sid, "status": "error"})
    return results


class DailySearchScheduler:
    def __init__(self, runner: Callable[..., Any] = stream_run) -> None:
        self._runner = runner
        self._task: asyncio.Task[Any] | None = None

    async def start(self, poll_seconds: int | None = None) -> None:
        secs = (
            get_config().daily_search_poll_seconds
            if poll_seconds is None
            else poll_seconds
        )
        if secs <= 0 or self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(secs))

    async def _loop(self, secs: int) -> None:
        while True:
            await asyncio.sleep(secs)
            try:
                await run_due_searches(runner=self._runner)
            except Exception:  # noqa: BLE001
                logger.warning("daily search sweep failed", exc_info=True)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001
                pass
            self._task = None


_scheduler: DailySearchScheduler | None = None


def get_scheduler() -> DailySearchScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = DailySearchScheduler()
    return _scheduler
```

- [ ] **Step 6: Run the scheduler tests to verify they pass**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_search_scheduler.py -q`
Expected: PASS (6 tests).

- [ ] **Step 7: Commit**

```bash
git add app/models.py app/db.py app/config.py app/services.py app/search_scheduler.py tests/test_search_scheduler.py
git commit -m "feat(search): daily job-search scheduler (opt-in per source, injectable runner)"
```

---

### Task 2: API endpoints + lifespan wiring

**Files:**
- Modify: `app/routers/job_sources.py` (create / patch / run-now)
- Modify: `app/main.py` (start/stop the scheduler)
- Test: `tests/test_job_sources_api.py` (create or extend)

**Interfaces:**
- Consumes: `services.upsert_job_source`, `search_scheduler.run_source_search`, `get_scheduler`.

- [ ] **Step 1: Write the failing API test**

Create `tests/test_job_sources_api.py` (or append if it exists):
```python
def test_job_source_create_patch_and_run(client, monkeypatch):
    # create
    r = client.post("/api/job-sources", json={
        "name": "LinkedIn ML", "kind": "job_board",
        "saved_query": "ml engineer remote", "auto_search": False,
    })
    assert r.status_code == 200, r.text
    sid = r.json()["id"]

    # patch: opt in
    r = client.patch(f"/api/job-sources/{sid}", json={"auto_search": True})
    assert r.status_code == 200
    assert r.json()["auto_search"] is True

    # run now (stub the agent runner so no web/CLI is hit)
    import app.routers.job_sources as mod

    async def fake_run_source_search(source_id, **kw):
        return {"source_id": source_id, "status": "ran"}

    monkeypatch.setattr(mod, "run_source_search", fake_run_source_search)
    r = client.post(f"/api/job-sources/{sid}/search")
    assert r.status_code == 200
    assert r.json()["status"] == "ran"

    # unknown id → 404
    assert client.patch("/api/job-sources/nope", json={"auto_search": True}).status_code == 404
    assert client.post("/api/job-sources/nope/search").status_code == 404
```

- [ ] **Step 2: Run it to verify it fails**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_job_sources_api.py -q`
Expected: FAIL (endpoints not defined → 405/404).

- [ ] **Step 3: Implement the endpoints**

Replace `app/routers/job_sources.py` with:
```python
"""Job-source endpoints — list, create, update (opt-in), and run a search now."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app import services
from app.db import get_session
from app.models import JobSource, JobSourceKind
from app.search_scheduler import run_source_search

router = APIRouter(prefix="/api/job-sources", tags=["job-sources"])


class JobSourceCreate(BaseModel):
    name: str
    kind: JobSourceKind = JobSourceKind.other
    url: str | None = None
    saved_query: str | None = None
    auto_search: bool = False
    notes: str | None = None


class JobSourceUpdate(BaseModel):
    name: str | None = None
    kind: JobSourceKind | None = None
    url: str | None = None
    saved_query: str | None = None
    auto_search: bool | None = None
    notes: str | None = None


@router.get("")
def list_job_sources(session: Session = Depends(get_session)) -> list[JobSource]:
    return services.list_job_sources(session)


@router.post("")
def create_job_source(
    body: JobSourceCreate, session: Session = Depends(get_session)
) -> JobSource:
    return services.upsert_job_source(
        session,
        name=body.name,
        kind=body.kind,
        url=body.url,
        saved_query=body.saved_query,
        auto_search=body.auto_search,
        notes=body.notes,
    )


@router.patch("/{source_id}")
def update_job_source(
    source_id: str, body: JobSourceUpdate, session: Session = Depends(get_session)
) -> JobSource:
    existing = session.get(JobSource, source_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="job source not found")
    return services.upsert_job_source(
        session,
        name=body.name if body.name is not None else existing.name,
        kind=body.kind,
        url=body.url,
        saved_query=body.saved_query,
        auto_search=body.auto_search,
        notes=body.notes,
        job_source_id=source_id,
    )


@router.post("/{source_id}/search")
async def search_now(
    source_id: str, session: Session = Depends(get_session)
) -> dict:
    if session.get(JobSource, source_id) is None:
        raise HTTPException(status_code=404, detail="job source not found")
    return await run_source_search(source_id)
```
NOTE: `upsert_job_source` requires `name`; for PATCH we pass the existing name when the body omits it (the matcher falls back to id via `job_source_id`).

- [ ] **Step 4: Wire the scheduler into the lifespan**

In `app/main.py` lifespan, after the keep-alive start, add the scheduler start, and stop it in the `finally`:
```python
    from app.search_scheduler import get_scheduler

    await get_scheduler().start()
```
and in `finally:` (alongside `await get_session().stop()`):
```python
        await get_scheduler().stop()
```

- [ ] **Step 5: Run the API test + full gate**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_job_sources_api.py -q` → PASS
Then: `bash scripts/ci/gate.sh` → GATE PASSED.

- [ ] **Step 6: Commit**

```bash
git add app/routers/job_sources.py app/main.py tests/test_job_sources_api.py
git commit -m "feat(search): job-source create/patch/run-now API + scheduler lifespan"
```

---

### Task 3: Frontend — Sources tab

**Files:**
- Modify: `frontend/lib/api.ts` (JobSource type fields + fetchers)
- Create: `frontend/app/components/SourcesTab.tsx`
- Modify: `frontend/app/page.tsx` (canvas union, nav button, render branch)

**Interfaces:**
- Consumes: `/api/job-sources` endpoints.

- [ ] **Step 1: api.ts**

In `frontend/lib/api.ts`: ensure the `JobSource` type includes `saved_query: string | null`, `auto_search: boolean`, and `last_checked_at: string | null` (add any missing fields). Add:
```ts
export async function createJobSource(body: {
  name: string;
  kind?: string;
  saved_query?: string | null;
  auto_search?: boolean;
}): Promise<JobSource> {
  const res = await fetch("/api/job-sources", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`create job source failed: ${res.status}`);
  return res.json();
}

export async function updateJobSource(
  id: string,
  body: { saved_query?: string | null; auto_search?: boolean; name?: string }
): Promise<JobSource> {
  const res = await fetch(`/api/job-sources/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`update job source failed: ${res.status}`);
  return res.json();
}

export async function runJobSourceSearch(id: string): Promise<{ status: string }> {
  const res = await fetch(`/api/job-sources/${id}/search`, { method: "POST" });
  if (!res.ok) throw new Error(`run search failed: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Create `SourcesTab.tsx`**

Model it on `frontend/app/components/ActionsTab.tsx` (read it for the list/add/Tailwind idiom). Create `frontend/app/components/SourcesTab.tsx` with: an add row (name + saved_query inputs, Add button → `createJobSource`); a list of sources, each showing name + kind, an editable `saved_query` input that calls `updateJobSource` on blur, an "Auto-search" checkbox toggling `auto_search` via `updateJobSource`, the `last_checked_at` (or "never"), and a "Search now" button calling `runJobSourceSearch` (disable + show "Searching…" while pending). Use `FetchError` on load failure (pattern from ActionsTab). Reload the list after each mutation. The component takes no props (sources aren't opportunity-scoped) — `export default function SourcesTab()`.

- [ ] **Step 3: Wire into `page.tsx`**

Read `frontend/app/page.tsx`; following the `InterviewsTab`/`ActionsTab` wiring pattern:
1. `import SourcesTab from "./components/SourcesTab";`
2. Add `| "sources"` to the `canvasTab` union.
3. Add a nav button labeled "Sources" (`onClick={() => setCanvasTab("sources")}`, same active-state classes as siblings).
4. Add a render branch `) : canvasTab === "sources" ? ( <SourcesTab /> )`.

- [ ] **Step 4: Build**

Run: `npm --prefix frontend install` (if needed) then `npm --prefix frontend run build` — must succeed.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/app/components/SourcesTab.tsx frontend/app/page.tsx
git commit -m "feat(search): Sources tab — manage saved queries, auto-search toggle, run now"
```
