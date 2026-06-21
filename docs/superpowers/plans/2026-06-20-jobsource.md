# JobSource Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attribute opportunities to a `JobSource` — `upsert_job_source`/`list_job_sources` service (incremental, optional opportunity linking), a `record_job_source` agent tool, `GET /api/job-sources` + `source` on detail, and a Source line in the Detail header.

**Architecture:** Backend mirrors company normalization (`upsert_company`/`record_company`/`companies.py` + the company-enrich opportunity link). Frontend adds a `JobSource` type + fetcher and a header Source line in `OpportunityDetailTab`. The `JobSource` model + `Opportunity.source_id` FK already exist.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, claude-agent-sdk MCP tools, pytest; Next.js/React/TypeScript frontend.

## Global Constraints

- `upsert_job_source` is INCREMENTAL: find-or-create (by `job_source_id`, else case-insensitive `name`, else create); only non-None args overwrite; `kind` set only when provided (default `other` on create). Sets `updated_at`.
- Optional `link_opportunity_id`: when set AND the opportunity exists, set `opp.source_id = row.id`; silent no-op on missing/None (mirrors `upsert_company`'s link).
- `record_job_source` passes `kind=None` when the arg is absent (forcing `other` would wipe an enriched kind).
- Writes via the agent tool only; `GET /api/job-sources` is read-only (no POST).
- Backend test-first (temp SQLite); `job_sources` is already wiped in `tests/conftest.py` `_clear_db`.
- Run backend tests with `.venv/bin/python -m pytest -q`; frontend verified with `npm --prefix frontend run build`.
- Follow patterns: `upsert_company` (service), `record_company` tool, `companies.py` (router), the Company line in `OpportunityDetailTab`.

---

### Task 1: Service — `upsert_job_source` + `list_job_sources`

**Files:**
- Modify: `app/services.py` (add `JobSource, JobSourceKind` to the `from app.models import (...)` block; add 2 functions)
- Test: `tests/test_job_source_service.py`

**Interfaces:**
- Produces: `upsert_job_source(session, *, name, kind: JobSourceKind | None = None, url=None, saved_query=None, notes=None, referrer_contact_id=None, last_checked_at=None, job_source_id: str | None = None, link_opportunity_id: str | None = None) -> JobSource`; `list_job_sources(session) -> list[JobSource]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_job_source_service.py
from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import JobSource, JobSourceKind, Opportunity, OpportunityType


def test_upsert_job_source_creates_then_matches_case_insensitive():
    with Session(engine) as s:
        a = services.upsert_job_source(s, name="LinkedIn", kind=JobSourceKind.job_board)
        b = services.upsert_job_source(s, name="linkedin", url="https://linkedin.com")
        assert a.id == b.id  # case-insensitive name match
        assert b.kind == JobSourceKind.job_board  # not wiped
        assert b.url == "https://linkedin.com"


def test_upsert_job_source_links_opportunity():
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        js = services.upsert_job_source(s, name="Referral", kind=JobSourceKind.referral,
                                        link_opportunity_id=opp.id)
        s.refresh(opp)
        assert opp.source_id == js.id


def test_upsert_job_source_link_missing_opp_is_noop():
    with Session(engine) as s:
        js = services.upsert_job_source(s, name="Indeed", link_opportunity_id="nope")
        assert js.id is not None  # did not raise


def test_list_job_sources_ordered():
    with Session(engine) as s:
        services.upsert_job_source(s, name="Zip")
        services.upsert_job_source(s, name=" angel")
        names = [j.name for j in services.list_job_sources(s)]
        assert names == ["angel", "Zip"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_job_source_service.py -v`
Expected: FAIL — `AttributeError: module 'app.services' has no attribute 'upsert_job_source'`.

- [ ] **Step 3: Write minimal implementation**

Add `JobSource, JobSourceKind` to the `from app.models import (...)` block in `app/services.py` (`func` and `Opportunity` are already imported from the company work). Append:

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
) -> JobSource:
    row = session.get(JobSource, job_source_id) if job_source_id else None
    if row is None:
        row = session.exec(
            select(JobSource).where(func.lower(JobSource.name) == name.strip().lower())
        ).first()
    if row is None:
        row = JobSource(name=name.strip())
    # Incremental: only non-None args overwrite.
    if kind is not None:
        row.kind = kind
    if url is not None:
        row.url = url
    if saved_query is not None:
        row.saved_query = saved_query
    if notes is not None:
        row.notes = notes
    if referrer_contact_id is not None:
        row.referrer_contact_id = referrer_contact_id
    if last_checked_at is not None:
        row.last_checked_at = last_checked_at
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    if link_opportunity_id:
        opp = session.get(Opportunity, link_opportunity_id)
        if opp is not None:
            opp.source_id = row.id
            session.add(opp)
            session.commit()
    return row


def list_job_sources(session: Session) -> list[JobSource]:
    return list(session.exec(select(JobSource).order_by(func.lower(JobSource.name))).all())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_job_source_service.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services.py tests/test_job_source_service.py
git commit -m "feat(services): upsert_job_source + list_job_sources"
```

---

### Task 2: Agent write-back tool — `record_job_source`

**Files:**
- Modify: `app/agent/tools.py` (add `JobSourceKind` to the models import; add `@tool`; add to `ALL_TOOLS`)
- Test: `tests/test_job_source_tool.py`

**Interfaces:**
- Consumes: `services.upsert_job_source` (Task 1).
- Produces: async tool `record_job_source(args) -> dict`; registered name `mcp__app__record_job_source`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_job_source_tool.py
from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.agent import tools
from app.db import engine
from app.models import JobSource, JobSourceKind, Opportunity, OpportunityType


@pytest.mark.asyncio
async def test_record_job_source_tool_creates_with_default_kind():
    res = await tools.record_job_source.handler({"name": "AngelList"})
    assert res["content"][0]["type"] == "text"
    with Session(engine) as s:
        row = s.exec(select(JobSource).where(JobSource.name == "AngelList")).one()
    assert row.kind == JobSourceKind.other


@pytest.mark.asyncio
async def test_record_job_source_tool_links_opportunity():
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        oid = opp.id
    await tools.record_job_source.handler(
        {"name": "Referral", "kind": "referral", "link_opportunity_id": oid}
    )
    with Session(engine) as s:
        linked = s.get(Opportunity, oid)
    assert linked.source_id is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_job_source_tool.py -v`
Expected: FAIL — `AttributeError: module 'app.agent.tools' has no attribute 'record_job_source'`.

- [ ] **Step 3: Write minimal implementation**

Add `JobSourceKind` to the `from app.models import (...)` block in `app/agent/tools.py`. Add this tool after `record_company`:

```python
@tool(
    "record_job_source",
    "Record or enrich where an opportunity came from (job board, referral, "
    "recruiter, saved search), optionally linking it to an opportunity.",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "kind": {
                "type": "string",
                "enum": ["job_board", "company_site", "referral", "recruiter",
                         "social", "aggregator", "other"],
            },
            "url": {"type": "string"},
            "saved_query": {"type": "string"},
            "notes": {"type": "string"},
            "referrer_contact_id": {"type": "integer"},
            "job_source_id": {"type": "string", "description": "set to enrich an existing source"},
            "link_opportunity_id": {
                "type": "string",
                "description": "set to attribute this opportunity to the source",
            },
        },
        "required": ["name"],
    },
)
async def record_job_source(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        kind = _enum(JobSourceKind, args["kind"], JobSourceKind.other) if args.get("kind") else None
        js = services.upsert_job_source(
            s,
            name=args["name"],
            kind=kind,
            url=args.get("url"),
            saved_query=args.get("saved_query"),
            notes=args.get("notes"),
            referrer_contact_id=args.get("referrer_contact_id"),
            job_source_id=args.get("job_source_id"),
            link_opportunity_id=args.get("link_opportunity_id"),
        )
        return _ok(f"Recorded job source {js.id}: {js.name}.")
```

Add `record_job_source` to the `ALL_TOOLS` list.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_job_source_tool.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/agent/tools.py tests/test_job_source_tool.py
git commit -m "feat(tools): record_job_source write-back tool"
```

---

### Task 3: API — job_sources router + detail include

**Files:**
- Create: `app/routers/job_sources.py`
- Modify: `app/main.py` (import + `include_router`)
- Modify: `app/routers/opportunities.py` (add `JobSource` to models import; add `source` to detail dict)
- Test: `tests/test_job_source_api.py`

**Interfaces:**
- Consumes: `services.list_job_sources`, `services.upsert_job_source` (Task 1).
- Produces: `GET /api/job-sources`; `source` key on `GET /api/opportunities/{id}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_job_source_api.py
from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import JobSourceKind, Opportunity, OpportunityType


def test_list_job_sources_endpoint(client):
    with Session(engine) as s:
        services.upsert_job_source(s, name="LinkedIn")
    res = client.get("/api/job-sources")
    assert res.status_code == 200 and any(j["name"] == "LinkedIn" for j in res.json())


def test_opportunity_detail_includes_source(client):
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        oid = opp.id
        services.upsert_job_source(s, name="Referral", kind=JobSourceKind.referral,
                                   link_opportunity_id=oid)

    detail = client.get(f"/api/opportunities/{oid}").json()
    assert "source" in detail and detail["source"] is not None
    assert detail["source"]["name"] == "Referral"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_job_source_api.py -v`
Expected: FAIL — `/api/job-sources` 404 / `KeyError: 'source'`.

- [ ] **Step 3a: Create the router**

```python
# app/routers/job_sources.py
"""Job-source endpoints — read path; attribution is written via the agent tool."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import services
from app.db import get_session
from app.models import JobSource

router = APIRouter(prefix="/api/job-sources", tags=["job-sources"])


@router.get("")
def list_job_sources(session: Session = Depends(get_session)) -> list[JobSource]:
    return services.list_job_sources(session)
```

- [ ] **Step 3b: Register in `app/main.py`**

Add `job_sources` to the `from app.routers import (...)` block (alphabetical), and add after a sibling include:
```python
app.include_router(job_sources.router)
```

- [ ] **Step 3c: Add the detail include in `app/routers/opportunities.py`**

Add `JobSource` to the `from app.models import (...)` block. In `get_opportunity`'s returned dict, beside `"company"`:
```python
        "source": session.get(JobSource, opp.source_id) if opp.source_id else None,
```

- [ ] **Step 4: Run new test, then full suite + gate**

Run: `.venv/bin/python -m pytest tests/test_job_source_api.py -v`
Expected: PASS (2 tests).
Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all).
Run: `scripts/ci/gate.sh`
Expected: GATE PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/routers/job_sources.py app/main.py app/routers/opportunities.py tests/test_job_source_api.py
git commit -m "feat(api): job-sources list + source on opportunity detail"
```

---

### Task 4: Frontend — JobSource type + fetcher + Detail Source line

**Files:**
- Modify: `frontend/lib/api.ts` (type + fetcher + `OpportunityDetail.source`)
- Modify: `frontend/app/components/OpportunityDetailTab.tsx` (header Source line)

**Interfaces:**
- Consumes: `GET /api/job-sources`; `OpportunityDetail.source` (the linked JobSource).
- Produces: `JobSource` type, `fetchJobSources()`, `<header Source line>`.

- [ ] **Step 1: Add the type + fetcher to `frontend/lib/api.ts`**

Append:

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

export async function fetchJobSources(): Promise<JobSource[]> {
  const res = await fetch("/api/job-sources");
  if (!res.ok) throw new Error(`job sources failed: ${res.status}`);
  return res.json();
}
```

In the existing `OpportunityDetail` type, add (beside `company`):
```typescript
  source: JobSource | null;
```

- [ ] **Step 2: Add the Source line to `OpportunityDetailTab.tsx`**

Read the file. In the header block (where the Company line `{detail.company && (...)}` renders), add a Source line below it, shown only when `detail.source` is set:

```tsx
        {detail.source && (
          <div className="text-xs text-slate-500">
            Source: <span className="font-medium">{detail.source.name}</span>
            {detail.source.kind && ` · ${detail.source.kind}`}
            {detail.source.url && (
              <>
                {" · "}
                <a
                  href={detail.source.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-600 underline"
                >
                  link
                </a>
              </>
            )}
          </div>
        )}
```

(Place it inside the header `div`, near the Company line — read the real markup first to match it.)

- [ ] **Step 3: Verify build + full backend suite + gate**

Run: `npm --prefix frontend run build`
Expected: "Compiled successfully", no type errors.
Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all).
Run: `scripts/ci/gate.sh`
Expected: GATE PASSED.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts frontend/app/components/OpportunityDetailTab.tsx
git commit -m "feat(ui): JobSource type + Source line in Detail header"
```

---

## Final verification

- [ ] `.venv/bin/python -m pytest -q` → all pass.
- [ ] `scripts/ci/gate.sh` → GATE PASSED.
- [ ] `npm --prefix frontend run build` → Compiled successfully.
- [ ] `git log --oneline` shows 4 focused commits on `feature/jobsource`.

## Self-Review (completed by plan author)

- **Spec coverage:** upsert (incremental + case-insensitive + link) + list (T1, spec §3); record_job_source tool with kind-when-present (T2, §4); GET router + detail `source` include (T3, §5); frontend type/fetcher + OpportunityDetail.source + Detail Source line (T4, §6–7); backend TDD + frontend build (§8).
- **Placeholder scan:** none — full code in every step; the Detail edit references the real Company-line markup (implementer reads the file first).
- **Type consistency:** `upsert_job_source(...)` signature identical across T1 def, T2 tool call. `JobSourceKind` enum values match model/tool/tests. `JobSource` TS fields match the serialized model columns. `source` key matches between backend (T3) and frontend (T4). `link_opportunity_id: str` ↔ `Opportunity.id: str`; `referrer_contact_id: int`. `.handler(...)` used to call the tool in tests.
