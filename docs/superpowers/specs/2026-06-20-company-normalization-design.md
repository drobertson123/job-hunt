# Design: Company Normalization

**Date:** 2026-06-20
**Status:** Approved design — ready for implementation plan
**Builds on:** the `Company` model + `company_id` FKs on opportunities/contacts
(added 2026-06-20), the application-tracking slice (pattern), and the existing
canvas-tab UI.

## 1. Purpose

Turn the loose `organization` strings on opportunities/contacts into reusable
`Company` rows linked via `company_id`, so company context is normalized,
queryable, and enrichable. Provides a service + agent tool to create/enrich
companies, a backfill that links existing rows, a read API, the company shown in
the opportunity Detail tab, and a Companies canvas tab.

## 2. Scope

A vertical slice: service (upsert + list + backfill), agent write-back tool,
read API + backfill endpoint + detail include, and frontend (Company type +
fetchers, Detail company line, Companies tab).

**Out of scope:** `GET /api/companies/{id}` (the Companies tab groups
opportunities client-side); domain-based dedup (name match only — opportunities
have no domains yet); company merge/dedup UI; editing companies from the UI
(writes go through the agent tool / backfill). Existing patterns are followed.

## 3. Service — `app/services.py`

```python
def upsert_company(
    session: Session,
    *,
    name: str,
    domain: str | None = None,
    industry: str | None = None,
    size: CompanySize | None = None,
    hq_location: str | None = None,
    careers_url: str | None = None,
    linkedin_url: str | None = None,
    ats_vendor: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
    company_id: str | None = None,
) -> Company: ...
```

Find-or-create + **incremental update** (mirrors `upsert_opportunity`'s
"only non-None fields overwrite" rule — deliberately NOT the full-overwrite of
`record_application`, so the agent can enrich one field without wiping others):
- If `company_id` given and found → use it. Else look up an existing company by
  **case-insensitive name** (`func.lower(Company.name) == name.strip().lower()`);
  if found, use it. Else create a new `Company(name=name.strip())`.
- For each optional arg that is non-None, set the column. `size` only set when
  provided (the model default `unknown` already applies on create). Set
  `updated_at = _utcnow()`. Commit, refresh, return.

```python
def list_companies(session: Session) -> list[Company]: ...  # ordered by name (case-insensitive)

def backfill_company_ids(session: Session) -> dict[str, int]: ...
```

`backfill_company_ids`:
- For each `Opportunity` where `organization` is a non-empty string and
  `company_id is None`: `c = upsert_company(name=organization)`; set
  `opp.company_id = c.id`.
- For each `Contact` where `organization` is non-empty and `company_id is None`:
  same.
- Idempotent (re-running links nothing new). Returns
  `{"opportunities_linked": n, "contacts_linked": m, "companies": total_company_count}`.

## 4. Agent write-back tool — `app/agent/tools.py`

New `@tool("record_company", ...)`, args: `name` (required), `domain`,
`industry`, `size` (enum: startup|smb|mid|large|enterprise|unknown),
`hq_location`, `careers_url`, `linkedin_url`, `ats_vendor`, `summary`, `notes`,
`company_id` (optional → update). Parse `size` with `_enum(CompanySize, ...,
CompanySize.unknown)` ONLY when present — to preserve incremental semantics, pass
`size=None` when the arg is absent (do not force `unknown` on update). Call
`services.upsert_company(...)`, return `_ok(...)`. Register in `ALL_TOOLS`.

## 5. API — `app/routers/companies.py` (new) + detail include

- `GET /api/companies` → `list[Company]` via `list_companies`.
- `POST /api/companies/backfill` → the `backfill_company_ids` dict.
- Register the router in `app/main.py`.
- Add `"company": session.get(Company, opp.company_id) if opp.company_id else None`
  to the `get_opportunity` detail dict.

No `GET /api/companies/{id}` — the Companies tab groups client-side.

## 6. Frontend — `frontend/lib/api.ts`

```typescript
export type Company = {
  id: string;
  name: string;
  domain: string | null;
  industry: string | null;
  size: string;
  hq_location: string | null;
  careers_url: string | null;
  linkedin_url: string | null;
  ats_vendor: string | null;
  summary: string | null;
  notes: string;
  created_at: string;
};

export async function fetchCompanies(): Promise<Company[]> { ... }       // GET /api/companies
export async function backfillCompanies(): Promise<{ opportunities_linked: number; contacts_linked: number; companies: number }> { ... } // POST /api/companies/backfill
```
- `OpportunityDetail` gains `company: Company | null`.

## 7. Frontend — components

- **`OpportunityDetailTab`**: in the header, when `detail.company` is set, show a
  small Company line: `name` · `industry` · `size` · `ats_vendor` and a careers
  link when present.
- **`CompaniesTab`** (new, prop `onOpen`): fetches `fetchCompanies()` +
  `fetchOpportunities()`; groups opportunities by `company_id`. Renders a
  **"Backfill from opportunities"** button (calls `backfillCompanies`, then
  refetches) and a list of company cards — each: `name` (+ industry/size/ats
  when present) and its linked opportunities as clickable rows (`onOpen(oppId)`
  → Detail). Companies with no linked opps still appear. Empty state when there
  are no companies.
- **`page.tsx`**: add `"companies"` to the `canvasTab` union, a "Companies" tab
  button (styled like the others), and render
  `<CompaniesTab onOpen={(id) => { setSelectedOpp(id); setCanvasTab("detail"); }} />`.

## 8. Testing

Backend test-first (deterministic temp SQLite):
1. **Service** (`tests/test_company_service.py`): `upsert_company` creates;
   case-insensitive name match reuses the same row; incremental update doesn't
   wipe unset fields; `list_companies` ordered; `backfill_company_ids` links an
   opportunity + a contact and is idempotent on a second run; an opportunity with
   no `organization` is skipped.
2. **Tool** (`tests/test_company_tool.py`): the tool creates a company + returns
   `_ok`; enriching by id updates without wiping.
3. **API** (`tests/test_company_api.py`): `GET /api/companies` lists;
   `POST /api/companies/backfill` returns counts and links rows; opportunity
   detail includes `company`.

Frontend verified via `npm --prefix frontend run build`. `companies` is already
wiped in `tests/conftest.py` `_clear_db` (registered with the relationship
models).

## 9. Notes / decisions

- **Incremental upsert** (non-None only) is the key semantic, distinct from
  `record_application`. The agent enriches companies over multiple calls.
- Name-based dedup is case-insensitive on a trimmed name; two orgs spelled
  differently produce two companies (acceptable — no fuzzy matching).
- The backfill is safe to run repeatedly; the live run on the 29 opportunities is
  a one-off demonstration, not part of the test suite.
- `Company` has `created_at`/`updated_at`; the TS type omits `updated_at` (not
  needed by the UI), consistent with other types.
