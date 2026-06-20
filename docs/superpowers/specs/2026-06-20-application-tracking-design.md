# Design: Application Tracking (full vertical slice)

**Date:** 2026-06-20
**Status:** Approved design — ready for implementation plan
**Builds on:** the `Application` model (table `applications`) added 2026-06-20.

## 1. Purpose

Let the agent record and update a job application (which opportunity, which
ATS/portal, status, external id), and surface applications in the API and UI.
First end-to-end use of the `Application` model.

## 2. Scope

Full vertical slice: service → agent write-back tool → API (list + detail
include) → frontend Applications tab. Backend is test-first.

**Out of scope:** per-opportunity detail view; manual create/edit from the UI
(writes go through the agent); status history/audit; bulk import; a pipeline
board. Existing patterns are followed (`add_action`/`record_action`,
`actions.py` router, `ArtifactCard`/tab wiring).

## 3. Service — `app/services.py`

Mirror `add_action`'s shape (keyword-only, commits, touches the opportunity).

```python
def record_application(
    session: Session,
    *,
    opportunity_id: str,
    status: ApplicationStatus = ApplicationStatus.draft,
    company_id: str | None = None,
    portal_url: str | None = None,
    external_id: str | None = None,
    submitted_at: datetime | None = None,
    login_hint: str | None = None,
    notes: str = "",
    application_id: str | None = None,
) -> Application: ...
```

Behavior:
- `application_id is None` → create a new `Application`.
- `application_id` given and found → set its columns from the args (the caller
  sends the full intended state) and `updated_at = _utcnow()`. If the id is not
  found, fall back to creating a new row.
- Either way, bump `opportunity.last_activity_at` when the opportunity exists
  (same as `add_action`).
- No fuzzy de-dup: one opportunity may have multiple applications; updates are
  explicit by id.

Also:
```python
def list_applications(
    session: Session, opportunity_id: str | None = None
) -> list[Application]: ...
```
Ordered `created_at` desc; filtered by `opportunity_id` when provided.

## 4. Agent write-back tool — `app/agent/tools.py`

Mirror `record_action`. New `@tool("record_application", ...)`:

- Args (JSON): `opportunity_id` (required), `status`, `company_id`, `portal_url`,
  `external_id`, `submitted_at`, `login_hint`, `notes`, `application_id` (optional
  → update).
- Parse `status` with the existing `_enum(ApplicationStatus, ..., ApplicationStatus.draft)`;
  parse `submitted_at` with `_parse_dt`.
- Open a session, call `services.record_application(...)`, return
  `_ok(f"Recorded application … ({status}) for opportunity {opportunity_id}")`.
- Register in the module's tool list and `build_app_mcp_server()` (the two places
  the other tools are listed).

## 5. API — `app/routers/applications.py` (new), mirrors `actions.py`

- `GET /api/applications` with optional `?opportunity_id=` → `list[Application]`
  via `services.list_applications`.
- Register the router in `app/main.py` next to the other routers.
- Extend `GET /api/opportunities/{opp_id}` (in `app/routers/opportunities.py`) to
  add `"applications": services.list_applications(session, opportunity_id=opp_id)`
  to the returned dict (one line, beside `actions`/`artifacts`/`decisions`).

No POST endpoint — creation/update is the agent tool's job (YAGNI).

## 6. Frontend — `frontend/lib/api.ts` + `frontend/app/components/ApplicationsTab.tsx`

`api.ts`:
```typescript
export type Application = {
  id: string;
  opportunity_id: string;
  company_id: string | null;
  status: string;
  portal_url: string | null;
  external_id: string | null;
  submitted_at: string | null;
  login_hint: string | null;
  notes: string;
  created_at: string;
};

export async function fetchApplications(): Promise<Application[]> { ... } // GET /api/applications
```
(Follow the exact fetch idiom already in `api.ts` — same base-URL/JSON handling
as `fetchOpportunities`.)

`ApplicationsTab.tsx`: fetches applications + opportunities (for titles), renders
a flat list. Each row: opportunity title (lookup by `opportunity_id`, fall back
to the id), a status badge, portal link (if any), submitted date (if any), notes.
Read-only. Empty state mirrors the Workspace empty state.

`page.tsx`: extend the `canvasTab` union with `"applications"`, add a third tab
button (`Applications ({applications.length})`), fetch applications in the
existing canvas load, and render `<ApplicationsTab .../>` when active. Reuse the
existing styling of the Workspace/Profile tab buttons.

## 7. Testing (TDD, backend only)

No frontend test harness exists (all tests are pytest); none is introduced
(YAGNI). Frontend is verified via the gate's lint/build.

1. **Service** (`tests/test_application_service.py`):
   - `record_application` with only `opportunity_id` → row created, `status`
     defaults `draft`, links to the opportunity, bumps `last_activity_at`.
   - `record_application(application_id=<existing>)` updates status/portal_url in
     place (same id, new values).
   - `list_applications(opportunity_id=...)` returns only that opportunity's rows.
2. **Tool** (`tests/test_application_tool.py`, mirror `tests/test_tools.py`):
   - Calling the `record_application` tool with a JSON args dict creates a row and
     returns an `_ok`-shaped result; a bad/missing `status` falls back to `draft`.
3. **API** (`tests/test_application_api.py`, mirror `tests/test_phase1_api.py`):
   - `GET /api/applications` returns created rows; `?opportunity_id=` filters.
   - `GET /api/opportunities/{id}` includes an `applications` key.

All deterministic (temp SQLite via `conftest`); `applications` already cleared
per-test (registered in `_clear_db`). No external API calls.

## 8. Notes / risks

- `record_application` "always set columns from args" on update means a caller
  must send the full intended state; acceptable because the agent constructs the
  call from context. `# ponytail:` comment marks this on the update branch.
- One opportunity → many applications is allowed; the UI lists each row.
- `submitted_at` is optional; status and submission are independent (you can be
  `interviewing` without a stored submit date).
