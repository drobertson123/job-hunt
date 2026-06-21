# Interview Calendar — Design

## Goal
Add and remove **calendar items for interviews**: schedule interview events tied
to an opportunity, view upcoming ones, remove them, and export each (or all
upcoming) as a standard **.ics** file importable into Google/Apple/Outlook —
without a hosted-calendar dependency.

## Why local + .ics (not Google Calendar API)
Constitution I (local-first, SQLite is the system of record; MUST NOT depend on
a hosted multi-tenant backend) rules out coupling the app to a Google OAuth
service the local agent can't reach anyway. The universal, dependency-free
interchange is iCalendar (.ics): the app owns the events; the user imports the
.ics into whatever calendar they use. "Add and remove" = CRUD on local events +
re-export. (Live two-way Google sync is a documented future option, not this
slice.)

## Data model — `InterviewEvent` (new table)
`app/models.py`:
- `id: int PK`
- `opportunity_id: str | None` FK `opportunities.id` (indexed)
- `title: str` (e.g. "Technical phone screen")
- `kind: InterviewKind` enum — `phone | video | onsite | technical | behavioral | final | other`
- `starts_at: datetime` (indexed; stored naive-UTC like the rest of the schema)
- `ends_at: datetime | None` (defaults to +1h in the .ics if absent)
- `location: str = ""` (address or video link)
- `notes: str = ""`
- `created_at: datetime`

New table → `init_db`'s `SQLModel.metadata.create_all` builds it; no migration.

## Service — `app/services.py`
- `add_interview(session, *, title, starts_at, opportunity_id=None, kind=other, ends_at=None, location="", notes="") -> InterviewEvent`
- `list_interviews(session, *, opportunity_id=None, upcoming=False) -> list[InterviewEvent]` (ordered by `starts_at`; `upcoming` filters `starts_at >= now`)
- `delete_interview(session, interview_id) -> bool`

## .ics — `app/ics.py`
`to_ics(events: list[InterviewEvent], *, now: datetime) -> str` builds a
`VCALENDAR` with one `VEVENT` per event: `UID interview-{id}@opportunity-hunter`,
`DTSTAMP`, `DTSTART`/`DTEND` (UTC `…Z`; `DTEND` = `ends_at` or `starts_at`+1h),
`SUMMARY`, `LOCATION`, `DESCRIPTION`. CRLF line endings; values escaped per
RFC 5545 (`\ ; , \n`). `now` injected (no `Date.now()` nondeterminism in tests).

## Agent tool — `app/agent/tools.py`
`schedule_interview` (mcp__app__) added to `ALL_TOOLS`: args `opportunity_id`,
`title` (required), `kind`, `starts_at` (ISO 8601, required), `ends_at`,
`location`, `notes` → `services.add_interview`. Lets the agent (e.g. the
email-analyser from goal #5) schedule interviews it finds in an email. Removal
stays human-only via the API (agents add, humans curate).

## API — `app/routers/interviews.py`
- `GET /api/interviews?opportunity_id=&upcoming=` → list
- `POST /api/interviews` (InterviewCreate) → create
- `DELETE /api/interviews/{id}` → 204 / 404
- `GET /api/interviews/{id}.ics` → single VEVENT (`text/calendar`, attachment)
- `GET /api/interviews.ics` → all upcoming (one VCALENDAR; subscribe/import)
Registered in `app/main.py`.

## UI — `frontend/app/components/InterviewsTab.tsx`
A new canvas tab (modeled on `ActionsTab`): an add row (opportunity select,
title, kind, `datetime-local` start, location) + a list of upcoming interviews
sorted by start, each with its opportunity link, formatted date/time, a
"Add to calendar" `.ics` download link, and a Remove button. A header
"Download all (.ics)" link to `/api/interviews.ics`. Wired into `page.tsx`
(canvas union, nav button + count badge, render branch). `api.ts` gains the
`Interview` type and `fetchInterviews`/`createInterview`/`deleteInterview`.

## Testing
- Service: add/list (ordering + `upcoming` filter)/delete round-trips.
- `to_ics`: contains `BEGIN:VCALENDAR`, a `VEVENT` per event, correct
  `DTSTART/DTEND` (absent `ends_at` → +1h), CRLF, and escaping of a `,`/`;` in a
  title; deterministic via injected `now`.
- API: POST→GET→DELETE lifecycle; `.ics` endpoints return `text/calendar` and a
  `BEGIN:VCALENDAR` body; unknown id → 404.
- Frontend: `next build` (type-check) — no unit harness exists.
Gate (`scripts/ci/gate.sh`) green. Constitution II honored: the agent writes
interviews only through the `schedule_interview` tool; UI CRUD uses direct
API→service (the established pattern for user-initiated writes, e.g. actions).
