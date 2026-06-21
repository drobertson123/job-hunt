# Company Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize `organization` strings into reusable `Company` rows: an incremental upsert service + backfill, a `record_company` agent tool, a read API + backfill endpoint + detail include, a Company line in the Detail tab, and a Companies canvas tab.

**Architecture:** Backend adds `upsert_company`/`list_companies`/`backfill_company_ids` to `services.py`, a `record_company` MCP tool, a `companies.py` router, and a `company` key on opportunity detail. Frontend adds a `Company` type + fetchers, a Company line in `OpportunityDetailTab`, and a `CompaniesTab`. The `Company` model + `company_id` FKs already exist.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, claude-agent-sdk MCP tools, pytest; Next.js/React/TypeScript frontend.

## Global Constraints

- `upsert_company` is INCREMENTAL: find-or-create (by `company_id`, else case-insensitive `name`, else create), then overwrite ONLY the args that are non-None (mirrors `upsert_opportunity`, NOT the full-overwrite of `record_application`). `size` is only set when provided.
- Writes go through the agent tool / backfill; API/UI are read-only except `POST /api/companies/backfill`.
- Backend test-first (deterministic temp SQLite); `companies` is already wiped in `tests/conftest.py` `_clear_db`.
- Run backend tests with `.venv/bin/python -m pytest -q`; frontend verified with `npm --prefix frontend run build`.
- Follow existing patterns: `upsert_opportunity` (service), `record_application` tool, `applications.py`/`actions.py` (router), `OpportunityDetailTab`/`ApplicationsTab` (components).

---

### Task 1: Service — upsert_company + list_companies + backfill

**Files:**
- Modify: `app/services.py` (add `from sqlalchemy import func`; add `Company, CompanySize, Contact` to the `from app.models import (...)` block; add 3 functions)
- Test: `tests/test_company_service.py`

**Interfaces:**
- Produces:
  - `upsert_company(session, *, name: str, domain=None, industry=None, size: CompanySize | None = None, hq_location=None, careers_url=None, linkedin_url=None, ats_vendor=None, summary=None, notes=None, company_id: str | None = None) -> Company`
  - `list_companies(session) -> list[Company]`
  - `backfill_company_ids(session) -> dict[str, int]` (keys: `opportunities_linked`, `contacts_linked`, `companies`)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_company_service.py
from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import (
    Company,
    CompanySize,
    Contact,
    Opportunity,
    OpportunityType,
)


def test_upsert_company_creates_then_matches_case_insensitive():
    with Session(engine) as s:
        a = services.upsert_company(s, name="Acme Corp", industry="Energy")
        b = services.upsert_company(s, name="acme corp", ats_vendor="Greenhouse")
        assert a.id == b.id  # case-insensitive name match → same row
        assert b.industry == "Energy"  # incremental: not wiped by the second call
        assert b.ats_vendor == "Greenhouse"
        assert b.size == CompanySize.unknown


def test_upsert_company_update_by_id_is_incremental():
    with Session(engine) as s:
        a = services.upsert_company(s, name="Globex", domain="globex.com")
        updated = services.upsert_company(s, name="Globex", company_id=a.id,
                                          industry="Manufacturing")
        assert updated.id == a.id
        assert updated.domain == "globex.com"  # untouched
        assert updated.industry == "Manufacturing"


def test_list_companies_ordered():
    with Session(engine) as s:
        services.upsert_company(s, name="Zeta")
        services.upsert_company(s, name="alpha")
        names = [c.name for c in services.list_companies(s)]
        assert names == ["alpha", "Zeta"]  # case-insensitive order


def test_backfill_links_opps_and_contacts_idempotently():
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role", organization="Initech")
        ct = Contact(name="Jane", organization="Initech")
        blank = Opportunity(type=OpportunityType.job, title="No org")  # organization None
        s.add(opp)
        s.add(ct)
        s.add(blank)
        s.commit()
        s.refresh(opp)
        s.refresh(ct)
        s.refresh(blank)

        result = services.backfill_company_ids(s)
        assert result["opportunities_linked"] == 1
        assert result["contacts_linked"] == 1
        s.refresh(opp)
        s.refresh(ct)
        s.refresh(blank)
        assert opp.company_id is not None and ct.company_id == opp.company_id
        assert blank.company_id is None  # no organization → skipped

        again = services.backfill_company_ids(s)
        assert again["opportunities_linked"] == 0 and again["contacts_linked"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_company_service.py -v`
Expected: FAIL — `AttributeError: module 'app.services' has no attribute 'upsert_company'`.

- [ ] **Step 3: Write minimal implementation**

In `app/services.py`: add `from sqlalchemy import func` near the imports, and add `Company, CompanySize, Contact` to the `from app.models import (...)` block. Append:

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
) -> Company:
    row = session.get(Company, company_id) if company_id else None
    if row is None:
        row = session.exec(
            select(Company).where(func.lower(Company.name) == name.strip().lower())
        ).first()
    if row is None:
        row = Company(name=name.strip())
    # Incremental: only non-None args overwrite (mirrors upsert_opportunity).
    if domain is not None:
        row.domain = domain
    if industry is not None:
        row.industry = industry
    if size is not None:
        row.size = size
    if hq_location is not None:
        row.hq_location = hq_location
    if careers_url is not None:
        row.careers_url = careers_url
    if linkedin_url is not None:
        row.linkedin_url = linkedin_url
    if ats_vendor is not None:
        row.ats_vendor = ats_vendor
    if summary is not None:
        row.summary = summary
    if notes is not None:
        row.notes = notes
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_companies(session: Session) -> list[Company]:
    return list(session.exec(select(Company).order_by(func.lower(Company.name))).all())


def backfill_company_ids(session: Session) -> dict[str, int]:
    opportunities_linked = 0
    for opp in session.exec(select(Opportunity)).all():
        if opp.organization and opp.organization.strip() and opp.company_id is None:
            c = upsert_company(session, name=opp.organization)
            opp.company_id = c.id
            session.add(opp)
            opportunities_linked += 1
    contacts_linked = 0
    for ct in session.exec(select(Contact)).all():
        if ct.organization and ct.organization.strip() and ct.company_id is None:
            c = upsert_company(session, name=ct.organization)
            ct.company_id = c.id
            session.add(ct)
            contacts_linked += 1
    session.commit()
    total = len(session.exec(select(Company)).all())
    return {
        "opportunities_linked": opportunities_linked,
        "contacts_linked": contacts_linked,
        "companies": total,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_company_service.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services.py tests/test_company_service.py
git commit -m "feat(services): upsert_company + list_companies + backfill"
```

---

### Task 2: Agent write-back tool — `record_company`

**Files:**
- Modify: `app/agent/tools.py` (add `CompanySize` to the models import; add `@tool`; add to `ALL_TOOLS`)
- Test: `tests/test_company_tool.py`

**Interfaces:**
- Consumes: `services.upsert_company` (Task 1).
- Produces: async tool `record_company(args) -> dict`; registered name `mcp__app__record_company`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_company_tool.py
from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.agent import tools
from app.db import engine
from app.models import Company


@pytest.mark.asyncio
async def test_record_company_tool_creates_and_enriches():
    res = await tools.record_company.handler({"name": "Wayne Ent", "industry": "Defense"})
    assert res["content"][0]["type"] == "text"
    with Session(engine) as s:
        row = s.exec(select(Company).where(Company.name == "Wayne Ent")).one()
        cid = row.id
        assert row.industry == "Defense"
    # enrich by id without wiping industry
    await tools.record_company.handler({"name": "Wayne Ent", "company_id": cid,
                                        "ats_vendor": "Lever"})
    with Session(engine) as s:
        row = s.get(Company, cid)
        assert row.industry == "Defense" and row.ats_vendor == "Lever"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_company_tool.py -v`
Expected: FAIL — `AttributeError: module 'app.agent.tools' has no attribute 'record_company'`.

- [ ] **Step 3: Write minimal implementation**

Add `CompanySize` to the `from app.models import (...)` block in `app/agent/tools.py`. Add this tool after `record_application`:

```python
@tool(
    "record_company",
    "Create or enrich a company (industry, size, ATS vendor, careers URL, ...). "
    "Only provided fields are updated; omit a field to leave it unchanged.",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "domain": {"type": "string"},
            "industry": {"type": "string"},
            "size": {
                "type": "string",
                "enum": ["startup", "smb", "mid", "large", "enterprise", "unknown"],
            },
            "hq_location": {"type": "string"},
            "careers_url": {"type": "string"},
            "linkedin_url": {"type": "string"},
            "ats_vendor": {"type": "string"},
            "summary": {"type": "string"},
            "notes": {"type": "string"},
            "company_id": {"type": "string", "description": "set to enrich an existing company"},
        },
        "required": ["name"],
    },
)
async def record_company(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        size = _enum(CompanySize, args["size"], CompanySize.unknown) if args.get("size") else None
        c = services.upsert_company(
            s,
            name=args["name"],
            domain=args.get("domain"),
            industry=args.get("industry"),
            size=size,
            hq_location=args.get("hq_location"),
            careers_url=args.get("careers_url"),
            linkedin_url=args.get("linkedin_url"),
            ats_vendor=args.get("ats_vendor"),
            summary=args.get("summary"),
            notes=args.get("notes"),
            company_id=args.get("company_id"),
        )
        return _ok(f"Recorded company {c.id}: {c.name}.")
```

Add `record_company` to the `ALL_TOOLS` list (after `record_application`).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_company_tool.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add app/agent/tools.py tests/test_company_tool.py
git commit -m "feat(tools): record_company write-back tool"
```

---

### Task 3: API — companies router + backfill + detail include

**Files:**
- Create: `app/routers/companies.py`
- Modify: `app/main.py` (import + `include_router`)
- Modify: `app/routers/opportunities.py` (add `Company` to models import; add `company` to detail dict)
- Test: `tests/test_company_api.py`

**Interfaces:**
- Consumes: `services.list_companies`, `services.backfill_company_ids`, `services.upsert_company` (Task 1).
- Produces: `GET /api/companies`, `POST /api/companies/backfill`; `company` key on `GET /api/opportunities/{id}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_company_api.py
from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import Opportunity, OpportunityType


def test_list_companies_endpoint(client):
    with Session(engine) as s:
        services.upsert_company(s, name="Acme")
    res = client.get("/api/companies")
    assert res.status_code == 200 and any(c["name"] == "Acme" for c in res.json())


def test_backfill_endpoint_links_and_detail_includes_company(client):
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role", organization="Initech")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        oid = opp.id

    res = client.post("/api/companies/backfill")
    assert res.status_code == 200
    assert res.json()["opportunities_linked"] == 1

    detail = client.get(f"/api/opportunities/{oid}").json()
    assert "company" in detail and detail["company"] is not None
    assert detail["company"]["name"] == "Initech"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_company_api.py -v`
Expected: FAIL — `/api/companies` 404 / `KeyError: 'company'`.

- [ ] **Step 3a: Create the router**

```python
# app/routers/companies.py
"""Companies endpoints — read + backfill; enrichment goes through the agent tool."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import services
from app.db import get_session
from app.models import Company

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("")
def list_companies(session: Session = Depends(get_session)) -> list[Company]:
    return services.list_companies(session)


@router.post("/backfill")
def backfill(session: Session = Depends(get_session)) -> dict:
    return services.backfill_company_ids(session)
```

- [ ] **Step 3b: Register in `app/main.py`**

Add `companies` to the `from app.routers import (...)` block (alphabetical), and after `app.include_router(communications.router)`:
```python
app.include_router(companies.router)
```

- [ ] **Step 3c: Add the detail include in `app/routers/opportunities.py`**

Add `Company` to the `from app.models import (...)` block. In `get_opportunity`'s returned dict, add beside `"communications"`:
```python
        "company": session.get(Company, opp.company_id) if opp.company_id else None,
```

- [ ] **Step 4: Run new test, then full suite + gate**

Run: `.venv/bin/python -m pytest tests/test_company_api.py -v`
Expected: PASS (2 tests).
Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all).
Run: `scripts/ci/gate.sh`
Expected: GATE PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/routers/companies.py app/main.py app/routers/opportunities.py tests/test_company_api.py
git commit -m "feat(api): companies list + backfill + detail include"
```

---

### Task 4: Frontend api.ts — Company type + fetchers + detail field

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Produces: `Company` type, `fetchCompanies()`, `backfillCompanies()`; adds `company: Company | null` to `OpportunityDetail`.

- [ ] **Step 1: Add the type + fetchers**

Append to `frontend/lib/api.ts`:

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

export async function fetchCompanies(): Promise<Company[]> {
  const res = await fetch("/api/companies");
  if (!res.ok) throw new Error(`companies failed: ${res.status}`);
  return res.json();
}

export async function backfillCompanies(): Promise<{
  opportunities_linked: number;
  contacts_linked: number;
  companies: number;
}> {
  const res = await fetch("/api/companies/backfill", { method: "POST" });
  if (!res.ok) throw new Error(`backfill failed: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Add `company` to `OpportunityDetail`**

In the existing `OpportunityDetail` type, add (beside `communications`):
```typescript
  company: Company | null;
```

- [ ] **Step 3: Verify it builds**

Run: `npm --prefix frontend run build`
Expected: "Compiled successfully", no type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(ui): Company type + fetchers + detail field"
```

---

### Task 5: Frontend — Company line in OpportunityDetailTab

**Files:**
- Modify: `frontend/app/components/OpportunityDetailTab.tsx`

**Interfaces:**
- Consumes: `OpportunityDetail.company` (Task 4).

- [ ] **Step 1: Add the Company line to the header**

Read the file. In the header block (where `o.organization`/`o.location`/`o.url` render), add a Company line below the summary, shown only when `detail.company` is set:

```tsx
        {detail.company && (
          <div className="text-xs text-slate-500">
            <span className="font-medium">{detail.company.name}</span>
            {detail.company.industry && ` · ${detail.company.industry}`}
            {detail.company.size && detail.company.size !== "unknown" && ` · ${detail.company.size}`}
            {detail.company.ats_vendor && ` · ATS: ${detail.company.ats_vendor}`}
            {detail.company.careers_url && (
              <>
                {" · "}
                <a
                  href={detail.company.careers_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-600 underline"
                >
                  careers
                </a>
              </>
            )}
          </div>
        )}
```

(Place it inside the header `div`, after the `{o.summary && ...}` line. Match the existing surrounding markup — read it first.)

- [ ] **Step 2: Verify it builds**

Run: `npm --prefix frontend run build`
Expected: "Compiled successfully", no type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/OpportunityDetailTab.tsx
git commit -m "feat(ui): show linked company in Detail header"
```

---

### Task 6: Frontend — CompaniesTab + page wiring

**Files:**
- Create: `frontend/app/components/CompaniesTab.tsx`
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `Company`, `Opportunity`, `fetchCompanies`, `backfillCompanies`, `fetchOpportunities` (api.ts); existing `selectedOpp`/`setSelectedOpp`/`setCanvasTab`.
- Produces: `<CompaniesTab onOpen={(oppId: string) => void} />`.

- [ ] **Step 1: Create `frontend/app/components/CompaniesTab.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Company,
  Opportunity,
  backfillCompanies,
  fetchCompanies,
  fetchOpportunities,
} from "@/lib/api";

export default function CompaniesTab({ onOpen }: { onOpen: (oppId: string) => void }) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    fetchCompanies().then(setCompanies).catch(() => setCompanies([]));
    fetchOpportunities().then(setOpps).catch(() => setOpps([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runBackfill = async () => {
    setBusy(true);
    try {
      await backfillCompanies();
      load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 text-sm">
      <button
        onClick={runBackfill}
        disabled={busy}
        className="self-start rounded bg-slate-900 px-3 py-1.5 text-xs text-white disabled:opacity-50"
      >
        {busy ? "Backfilling…" : "Backfill from opportunities"}
      </button>

      {companies.length === 0 ? (
        <p className="text-slate-400">No companies yet. Run backfill or let the agent add them.</p>
      ) : (
        companies.map((c) => {
          const linked = opps.filter((o) => o.organization === c.name);
          return (
            <div key={c.id} className="rounded border border-slate-200 p-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{c.name}</span>
                {c.industry && <span className="text-xs text-slate-500">{c.industry}</span>}
                {c.size && c.size !== "unknown" && (
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{c.size}</span>
                )}
                {c.ats_vendor && (
                  <span className="text-xs text-slate-400">ATS: {c.ats_vendor}</span>
                )}
              </div>
              {linked.map((o) => (
                <div
                  key={o.id}
                  onClick={() => onOpen(o.id)}
                  className="mt-1 cursor-pointer text-xs text-blue-600 hover:underline"
                >
                  {o.title}
                </div>
              ))}
            </div>
          );
        })
      )}
    </div>
  );
}
```

(Note: grouping is by `o.organization === c.name` because the dropdown `Opportunity` type does not include `company_id`; the org string is what the backfill matched on. This is acceptable for the overview.)

- [ ] **Step 2: Wire into `frontend/app/page.tsx`**

Read `page.tsx` first. Then:
1. Import: `import CompaniesTab from "./components/CompaniesTab";`
2. Widen the `canvasTab` union (the existing multi-line `useState`) to add `"companies"`.
3. Add a "Companies" tab button after the Attention button (verbatim style — copy the exact className expression, substituting `"companies"`):
```tsx
            <button
              className={`border-b-2 py-2 ${
                canvasTab === "companies"
                  ? "border-slate-900 text-slate-900"
                  : "border-transparent text-slate-400 hover:text-slate-600"
              }`}
              onClick={() => setCanvasTab("companies")}
            >
              Companies
            </button>
```
4. Add a render branch before the workspace `) : (`:
```tsx
          ) : canvasTab === "companies" ? (
            <CompaniesTab
              onOpen={(id) => {
                setSelectedOpp(id);
                setCanvasTab("detail");
              }}
            />
```

Do NOT add companies state to `page.tsx`; leave the workspace block and other tabs unchanged.

- [ ] **Step 3: Verify build + full backend suite + gate**

Run: `npm --prefix frontend run build`
Expected: "Compiled successfully", no type errors.
Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all).
Run: `scripts/ci/gate.sh`
Expected: GATE PASSED.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/CompaniesTab.tsx frontend/app/page.tsx
git commit -m "feat(ui): Companies canvas tab with backfill"
```

---

## Final verification

- [ ] `.venv/bin/python -m pytest -q` → all pass.
- [ ] `scripts/ci/gate.sh` → GATE PASSED.
- [ ] `npm --prefix frontend run build` → Compiled successfully.
- [ ] `git log --oneline` shows 6 focused commits on `feature/company-normalization`.

## Self-Review (completed by plan author)

- **Spec coverage:** incremental upsert + case-insensitive match + list + backfill (T1, spec §3); record_company tool with size-when-present (T2, §4); GET/POST-backfill API + detail include (T3, §5); frontend type/fetchers + OpportunityDetail.company (T4, §6); Detail company header line (T5, §7); CompaniesTab + backfill button + page wiring (T6, §7); backend TDD + frontend build (T1–T6, §8).
- **Placeholder scan:** none — full code in every code step; component edits reference the real header markup / tab pattern (implementer reads the file first).
- **Type consistency:** `upsert_company(...)` signature identical across T1 def, T2 tool call. `CompanySize` enum string values match model/tool/tests. `Company` TS fields match the model's serialized columns. `company`/`opportunities_linked`/`contacts_linked`/`companies` keys match between backend (T3) and frontend (T4/T6). `.handler(...)` used to call the tool in tests (consistent with `test_application_tool.py`). CompaniesTab groups by `o.organization === c.name` since the dropdown `Opportunity` type lacks `company_id` (documented).
