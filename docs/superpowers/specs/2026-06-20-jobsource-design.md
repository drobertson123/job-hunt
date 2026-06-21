# Design: JobSource Attribution

**Date:** 2026-06-20
**Status:** Approved design — ready for implementation plan
**Builds on:** the `JobSource` model + `Opportunity.source_id` FK, company
normalization (pattern, incl. opportunity linking), and the Detail tab.

## 1. Purpose

Attribute where an opportunity came from — a job board, a referral, a recruiter,
a saved search. The `JobSource` model exists with no service/tool/API/UI; this
adds the full surface and links opportunities via `source_id`. Completes all five
relationship models with vertical slices.

## 2. Scope

Backend: `upsert_job_source`/`list_job_sources` service (incremental, optional
opportunity linking), a `record_job_source` agent tool, a `GET /api/job-sources`
router + `source` on opportunity detail. Frontend: a `JobSource` type + fetcher
and a Source line in `OpportunityDetailTab`'s header.

**Out of scope:** backfill (the existing `source` strings — paste/url/discovery/
manual/agent — are too coarse to map to named sources); a JobSources tab; manual
UI create; saved-feed polling. Follows the company-normalization pattern.

## 3. Service — `app/services.py`

Mirror `upsert_company` (incremental, case-insensitive name dedup, optional link):

```python
def upsert_job_source(
    session: Session,
    *,
    name: str,
    kind: JobSourceKind | None = None,
    url: str | None = None,
    saved_query: str | None = None,
    notes: str | None = None,
    referrer_contact_id: int | None = None,
    last_checked_at: datetime | None = None,
    job_source_id: str | None = None,
    link_opportunity_id: str | None = None,
) -> JobSource: ...
```

- Find-or-create: by `job_source_id`, else case-insensitive `name`
  (`func.lower(JobSource.name) == name.strip().lower()`), else create. Only
  non-None args overwrite (`kind` only when provided; default `other` applies on
  create). Set `updated_at = _utcnow()`.
- After upsert, if `link_opportunity_id` is set AND the opportunity exists, set
  `opp.source_id = row.id` (silent no-op on missing/None — like
  `upsert_company`'s link).

```python
def list_job_sources(session: Session) -> list[JobSource]: ...  # ordered by name (case-insensitive)
```

## 4. Agent write-back tool — `app/agent/tools.py`

New `@tool("record_job_source", ...)`, args: `name` (required), `kind` (enum:
job_board|company_site|referral|recruiter|social|aggregator|other), `url`,
`saved_query`, `notes`, `referrer_contact_id` (int), `job_source_id` (→ update),
`link_opportunity_id`. Parse `kind` with `_enum(JobSourceKind, ...,
JobSourceKind.other)` only when present (pass `None` when absent, preserving
incremental semantics). Call `services.upsert_job_source(...)`, return `_ok(...)`.
Registered in `ALL_TOOLS`.

## 5. API — `app/routers/job_sources.py` (new) + detail include

- `GET /api/job-sources` → `list[JobSource]` via `list_job_sources`.
- Register the router in `app/main.py`.
- Add `"source": session.get(JobSource, opp.source_id) if opp.source_id else None`
  to the `get_opportunity` detail dict.

No POST (no manual UI create) — attribution is agent-written via the tool.

## 6. Frontend — `frontend/lib/api.ts`

```typescript
export type JobSource = {
  id: string;
  name: string;
  kind: string;
  url: string | null;
  saved_query: string | null;
  last_checked_at: string | null;
  referrer_contact_id: number | null;
  notes: string;
  created_at: string;
};

export async function fetchJobSources(): Promise<JobSource[]> { ... }  // GET /api/job-sources
```
- `OpportunityDetail` gains `source: JobSource | null`.

## 7. Frontend — `OpportunityDetailTab`

In the header, when `detail.source` is set, show a Source line:
`Source: <name>` · `<kind>` · the `url` as an external link when present. Mirror
the existing Company line placement (a small `text-xs` muted row in the header).

## 8. Testing

Backend test-first (deterministic temp SQLite; `job_sources` already wiped in
`tests/conftest.py` `_clear_db`):
1. **Service** (`tests/test_job_source_service.py`): `upsert_job_source` creates;
   case-insensitive name match reuses; incremental update doesn't wipe unset
   fields; `link_opportunity_id` sets `opportunity.source_id` (no-op when
   missing); `list_job_sources` ordered.
2. **Tool** (`tests/test_job_source_tool.py`): the tool creates a row + returns
   `_ok`; `kind` defaults to `other` when omitted; links the opportunity when
   `link_opportunity_id` is passed.
3. **API** (`tests/test_job_source_api.py`): `GET /api/job-sources` lists;
   opportunity detail includes `source` (null when unlinked, the JobSource when
   linked).

Frontend verified via `npm --prefix frontend run build`.

## 9. Notes

- `JobSource` has `updated_at` (unlike Contact/Communication), so `upsert_job_source`
  sets it — same as `upsert_company`.
- `kind` incremental handling mirrors `record_company`'s `size`: pass `None` when
  the arg is absent so an existing kind isn't reset to `other` on enrichment.
- Linking sets `Opportunity.source_id`; the detail `source` include reads it back.
