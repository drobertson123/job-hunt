# Automated Daily Job Searches — Design

## Goal
Automatically run job-discovery searches every day for the saved queries the
user opts in, adding any genuinely-new postings to the pipeline — without an
external cron/systemd dependency.

## Approach (local-first, in-process)
Mirror the persistent-session keep-alive (#4): an in-process background
scheduler in the FastAPI app. It is **inert until the user opts a source in** —
each `JobSource` gets an `auto_search` toggle (default off); the scheduler only
runs sources where `auto_search` is on, a `saved_query` is set, and the last run
was over `interval_hours` ago. No global on/off flag is needed — the per-source
toggle is the switch, so nothing spends tokens until the user enables it.

The search itself reuses the existing agent path: the scheduler runs a
prompt-driven agent turn (`stream_run`) that uses `WebSearch`/`WebFetch` and
calls `mcp__app__save_opportunity`. Dedup is free — `save_opportunity` is an
idempotent upsert on `dedupe_key` (the posting URL), so re-finding a posting on
a later day does not create a duplicate. No new skill/capability is added.

## Model — `JobSource.auto_search`
Add `auto_search: bool = False` to `JobSource` (existing `saved_query` and
`last_checked_at` columns already exist). Migration: `_ensure_column(engine,
"job_sources", "auto_search", "BOOLEAN DEFAULT 0")`.

## Service — `app/services.py`
- Extend `upsert_job_source(...)` with an `auto_search: bool | None = None`
  parameter (incremental, like the others).
- `list_job_sources` unchanged.

## Scheduler — `app/search_scheduler.py`
- `build_search_prompt(saved_query: str) -> str` — the discovery instruction
  (search job boards for the query; save each new posting via
  `save_opportunity` with `type="job"`, `dedupe_key=url`, `source="daily-search"`;
  never fabricate a posting or URL).
- `due_job_sources(session, *, now, interval_hours) -> list[JobSource]` — sources
  with `auto_search` true, a non-empty `saved_query`, and
  `last_checked_at is None or last_checked_at < now - interval_hours`.
- `async run_source_search(source_id, *, runner=stream_run, now=None) -> dict` —
  build the prompt from the source's `saved_query`, drive the agent turn to
  completion, then stamp `last_checked_at = now`. Returns a small status dict.
- `async run_due_searches(*, now=None, runner=stream_run) -> list[dict]` — run
  each due source serially.
- `DailySearchScheduler` — a background loop (started in lifespan, stopped on
  shutdown) that every `daily_search_poll_seconds` calls `run_due_searches`.
  Best-effort: a failed run is logged, never crashes the app. `runner` is
  injectable so tests drive it with a fake agent (no web/CLI/tokens).

## Config — `app/config.py`
- `daily_search_interval_hours: int = 24`
- `daily_search_poll_seconds: int = 3600` (how often the loop checks for due work)

## API — `app/routers/job_sources.py`
- `POST /api/job-sources` — create (name, kind, url, saved_query, auto_search).
- `PATCH /api/job-sources/{id}` — update (saved_query, auto_search, name, …).
- `POST /api/job-sources/{id}/search` — run a search now (awaits one run);
  404 if unknown.
- `GET` (existing) returns `last_checked_at` + `auto_search` for display.

## Lifespan — `app/main.py`
Start the scheduler after `init_db()`/keep-alive; stop it on shutdown.

## UI — `frontend/app/components/SourcesTab.tsx`
A new canvas tab "Sources": list job sources (name, kind, `saved_query`,
`auto_search` toggle, last-checked), an add form, a per-row "Search now" button,
and inline editing of the saved query + toggle. `api.ts` gains
`createJobSource`/`updateJobSource`/`runJobSourceSearch`. Wired into `page.tsx`
(canvas union, nav button, render branch).

## Testing
- `due_job_sources`: respects `auto_search`, empty `saved_query`, and the
  `interval_hours` cutoff (null last-checked is always due).
- `run_source_search`: drives an injected fake runner, asserts the prompt
  contains the `saved_query` and `last_checked_at` is stamped.
- `run_due_searches`: runs exactly the due sources (injected runner).
- `DailySearchScheduler.start/stop`: idempotent start, clean cancellation.
- API: create → PATCH toggle → run-now (injected/monkeypatched runner) → list
  reflects state; unknown id → 404.
- Frontend: `next build`.
Gate green. Constitution II honored — discovery writes only through
`save_opportunity`; the scheduler stamps `last_checked_at` via the service.
