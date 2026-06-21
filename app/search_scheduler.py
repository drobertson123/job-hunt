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
