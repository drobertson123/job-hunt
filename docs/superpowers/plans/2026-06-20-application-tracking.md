# Application Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the agent record/update job applications and surface them via API and a frontend Applications tab.

**Architecture:** A `record_application`/`list_applications` service pair (mirrors `add_action`), an agent write-back `@tool` (mirrors `record_action`), a read-only `/api/applications` router (mirrors `actions.py`) plus an `applications` include on the opportunity-detail endpoint, and a read-only Applications canvas tab in the Next.js frontend. The `Application` model already exists.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, claude-agent-sdk in-process MCP tools, pytest; Next.js/React/TypeScript/Tailwind frontend.

## Global Constraints

- Writes go through the agent tool only; the API/UI are read-only (no POST). (spec §2, §5)
- Backend is test-first (pytest, deterministic temp SQLite via `tests/conftest.py`). No frontend test harness exists and none is added. (spec §7)
- Run backend tests with `.venv/bin/python -m pytest -q` (worktree shares the primary checkout's `.venv`).
- The local gate (`scripts/ci/gate.sh`) runs pytest only for this repo (ruff/frontend-lint skip); the frontend is verified explicitly with `npm --prefix frontend run build`.
- `applications` is already registered in `tests/conftest.py` `_clear_db`, so rows are wiped per test.
- Follow existing patterns exactly: `add_action` (service), `record_action` (tool), `actions.py` (router), `fetchArtifacts` (api client).

---

### Task 1: Service — `record_application` + `list_applications`

**Files:**
- Modify: `app/services.py` (add two functions; extend the `app.models` import)
- Test: `tests/test_application_service.py` (create)

**Interfaces:**
- Consumes: existing `Application`, `ApplicationStatus`, `Opportunity` models; `_utcnow`, `select`, `Session` already used in `app/services.py`.
- Produces:
  - `record_application(session, *, opportunity_id: str, status: ApplicationStatus = ApplicationStatus.draft, company_id=None, portal_url=None, external_id=None, submitted_at=None, login_hint=None, notes="", application_id: str | None = None) -> Application`
  - `list_applications(session, opportunity_id: str | None = None) -> list[Application]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_application_service.py
from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import ApplicationStatus, Opportunity, OpportunityType


def _make_opp(s: Session) -> Opportunity:
    opp = Opportunity(type=OpportunityType.job, title="Staff ML Engineer")
    s.add(opp)
    s.commit()
    s.refresh(opp)
    return opp


def test_record_application_creates_with_defaults_and_touches_opp():
    with Session(engine) as s:
        opp = _make_opp(s)
        before = opp.last_activity_at
        app_row = services.record_application(
            s, opportunity_id=opp.id, portal_url="https://boards.greenhouse.io/x"
        )
        assert app_row.id is not None
        assert app_row.opportunity_id == opp.id
        assert app_row.status == ApplicationStatus.draft
        s.refresh(opp)
        assert opp.last_activity_at >= before


def test_record_application_updates_existing_by_id():
    with Session(engine) as s:
        opp = _make_opp(s)
        a = services.record_application(s, opportunity_id=opp.id)
        updated = services.record_application(
            s, opportunity_id=opp.id, status=ApplicationStatus.submitted,
            portal_url="https://lever.co/y", application_id=a.id,
        )
        assert updated.id == a.id
        assert updated.status == ApplicationStatus.submitted
        assert updated.portal_url == "https://lever.co/y"
        assert len(services.list_applications(s, opportunity_id=opp.id)) == 1


def test_list_applications_filters_by_opportunity():
    with Session(engine) as s:
        o1, o2 = _make_opp(s), _make_opp(s)
        services.record_application(s, opportunity_id=o1.id)
        services.record_application(s, opportunity_id=o2.id)
        assert len(services.list_applications(s, opportunity_id=o1.id)) == 1
        assert len(services.list_applications(s)) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_application_service.py -v`
Expected: FAIL with `AttributeError: module 'app.services' has no attribute 'record_application'`.

- [ ] **Step 3: Write minimal implementation**

In `app/services.py`, add `Application, ApplicationStatus` to the existing `from app.models import (...)` block. Then append:

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
) -> Application:
    app_row = session.get(Application, application_id) if application_id else None
    if app_row is None:
        app_row = Application(opportunity_id=opportunity_id)
    # ponytail: full overwrite from args — caller sends the intended state.
    app_row.opportunity_id = opportunity_id
    app_row.status = status
    app_row.company_id = company_id
    app_row.portal_url = portal_url
    app_row.external_id = external_id
    app_row.submitted_at = submitted_at
    app_row.login_hint = login_hint
    app_row.notes = notes
    app_row.updated_at = _utcnow()
    session.add(app_row)
    opp = session.get(Opportunity, opportunity_id)
    if opp:
        opp.last_activity_at = _utcnow()
        session.add(opp)
    session.commit()
    session.refresh(app_row)
    return app_row


def list_applications(
    session: Session, opportunity_id: str | None = None
) -> list[Application]:
    q = select(Application)
    if opportunity_id:
        q = q.where(Application.opportunity_id == opportunity_id)
    return list(session.exec(q.order_by(Application.created_at.desc())).all())
```

(If `datetime` is not already imported in `app/services.py`, it is — `add_action` uses `due_at: datetime`. `select` and `_utcnow` are used by `list_opportunities`/`add_action`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_application_service.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services.py tests/test_application_service.py
git commit -m "feat(services): record_application + list_applications"
```

---

### Task 2: Agent write-back tool — `record_application`

**Files:**
- Modify: `app/agent/tools.py` (add `ApplicationStatus` import; add `@tool`; add to `ALL_TOOLS`)
- Test: `tests/test_application_tool.py` (create)

**Interfaces:**
- Consumes: `services.record_application` (Task 1); existing `_enum`, `_parse_dt`, `_ok`, `Session`, `engine`.
- Produces: async tool fn `record_application(args: dict) -> dict`; registered name `mcp__app__record_application`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_application_tool.py
from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.agent import tools
from app.db import engine
from app.models import Application, ApplicationStatus, Opportunity, OpportunityType


def _make_opp() -> str:
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        return opp.id


@pytest.mark.asyncio
async def test_record_application_tool_creates_row():
    opp_id = _make_opp()
    res = await tools.record_application(
        {"opportunity_id": opp_id, "status": "submitted",
         "portal_url": "https://boards.greenhouse.io/x"}
    )
    assert res["content"][0]["type"] == "text"
    with Session(engine) as s:
        rows = s.exec(select(Application).where(Application.opportunity_id == opp_id)).all()
    assert len(rows) == 1 and rows[0].status == ApplicationStatus.submitted


@pytest.mark.asyncio
async def test_record_application_tool_bad_status_defaults_draft():
    opp_id = _make_opp()
    await tools.record_application({"opportunity_id": opp_id, "status": "bogus"})
    with Session(engine) as s:
        row = s.exec(select(Application).where(Application.opportunity_id == opp_id)).one()
    assert row.status == ApplicationStatus.draft
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_application_tool.py -v`
Expected: FAIL with `AttributeError: module 'app.agent.tools' has no attribute 'record_application'`.

- [ ] **Step 3: Write minimal implementation**

In `app/agent/tools.py`, add `ApplicationStatus` to the `from app.models import (...)` block. Add this tool after `record_action`:

```python
@tool(
    "record_application",
    "Record or update a job application to an opportunity (ATS/portal + status).",
    {
        "type": "object",
        "properties": {
            "opportunity_id": {"type": "string"},
            "status": {
                "type": "string",
                "enum": ["draft", "submitted", "under_review", "interviewing",
                         "offer", "rejected", "withdrawn"],
            },
            "company_id": {"type": "string"},
            "portal_url": {"type": "string"},
            "external_id": {"type": "string"},
            "submitted_at": {"type": "string", "description": "ISO 8601 datetime"},
            "login_hint": {"type": "string"},
            "notes": {"type": "string"},
            "application_id": {
                "type": "string",
                "description": "set to update an existing application",
            },
        },
        "required": ["opportunity_id"],
    },
)
async def record_application(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        app_row = services.record_application(
            s,
            opportunity_id=args["opportunity_id"],
            status=_enum(ApplicationStatus, args.get("status"), ApplicationStatus.draft),
            company_id=args.get("company_id"),
            portal_url=args.get("portal_url"),
            external_id=args.get("external_id"),
            submitted_at=_parse_dt(args.get("submitted_at")),
            login_hint=args.get("login_hint"),
            notes=args.get("notes") or "",
            application_id=args.get("application_id"),
        )
        return _ok(
            f"Recorded application {app_row.id} "
            f"({app_row.status.value}) for opportunity {app_row.opportunity_id}."
        )
```

Add `record_application` to the `ALL_TOOLS` list (after `record_action`).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_application_tool.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/agent/tools.py tests/test_application_tool.py
git commit -m "feat(tools): record_application write-back tool"
```

---

### Task 3: API — applications router + detail include

**Files:**
- Create: `app/routers/applications.py`
- Modify: `app/main.py` (import + `include_router`)
- Modify: `app/routers/opportunities.py` (add `applications` to the detail dict)
- Test: `tests/test_application_api.py` (create)

**Interfaces:**
- Consumes: `services.record_application`, `services.list_applications` (Task 1).
- Produces: `GET /api/applications` (optional `?opportunity_id=`) → `list[Application]`; `applications` key on `GET /api/opportunities/{id}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_application_api.py
from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import Opportunity, OpportunityType


def _seed() -> str:
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        services.record_application(s, opportunity_id=opp.id, portal_url="https://x")
        return opp.id


def test_list_applications_endpoint(client):
    opp_id = _seed()
    res = client.get("/api/applications")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1 and data[0]["opportunity_id"] == opp_id

    res2 = client.get("/api/applications", params={"opportunity_id": opp_id})
    assert res2.status_code == 200 and len(res2.json()) == 1


def test_opportunity_detail_includes_applications(client):
    opp_id = _seed()
    res = client.get(f"/api/opportunities/{opp_id}")
    assert res.status_code == 200
    body = res.json()
    assert "applications" in body and len(body["applications"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_application_api.py -v`
Expected: FAIL — `/api/applications` 404 (router not registered) / `KeyError: 'applications'`.

- [ ] **Step 3a: Create the router**

```python
# app/routers/applications.py
"""Applications endpoints — read path; writes go through the agent tool."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import services
from app.db import get_session
from app.models import Application

router = APIRouter(prefix="/api/applications", tags=["applications"])


@router.get("")
def list_applications(
    opportunity_id: str | None = None,
    session: Session = Depends(get_session),
) -> list[Application]:
    return services.list_applications(session, opportunity_id=opportunity_id)
```

- [ ] **Step 3b: Register the router in `app/main.py`**

Add `applications` to the `from app.routers import (...)` block, and add after `app.include_router(actions.router)`:

```python
app.include_router(applications.router)
```

- [ ] **Step 3c: Add the detail include in `app/routers/opportunities.py`**

In `get_opportunity`'s returned dict, add a line beside `"actions"`:

```python
        "applications": services.list_applications(session, opportunity_id=opp_id),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_application_api.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full suite + gate**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all prior + new).
Run: `scripts/ci/gate.sh`
Expected: GATE PASSED.

- [ ] **Step 6: Commit**

```bash
git add app/routers/applications.py app/main.py app/routers/opportunities.py tests/test_application_api.py
git commit -m "feat(api): list applications + include on opportunity detail"
```

---

### Task 4: Frontend — Applications tab

**Files:**
- Modify: `frontend/lib/api.ts` (add `Application` type + `fetchApplications`)
- Create: `frontend/app/components/ApplicationsTab.tsx`
- Modify: `frontend/app/page.tsx` (tab union, state, fetch, button, render)

**Interfaces:**
- Consumes: `GET /api/applications` (Task 3); existing `Opportunity` type and `fetchOpportunities`.
- Produces: `Application` TS type, `fetchApplications()`, `<ApplicationsTab />`.

- [ ] **Step 1: Add the type + fetch to `frontend/lib/api.ts`**

After the `Artifact` type, add:

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
```

After `fetchArtifacts`, add (same idiom):

```typescript
export async function fetchApplications(): Promise<Application[]> {
  const res = await fetch("/api/applications");
  if (!res.ok) throw new Error(`applications failed: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Create `frontend/app/components/ApplicationsTab.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import {
  Application,
  Opportunity,
  fetchApplications,
  fetchOpportunities,
} from "@/lib/api";

export default function ApplicationsTab() {
  const [apps, setApps] = useState<Application[]>([]);
  const [opps, setOpps] = useState<Opportunity[]>([]);

  useEffect(() => {
    fetchApplications().then(setApps).catch(() => setApps([]));
    fetchOpportunities().then(setOpps).catch(() => setOpps([]));
  }, []);

  if (apps.length === 0) {
    return (
      <p className="p-4 text-sm text-gray-500">
        Applications the agent records will appear here.
      </p>
    );
  }

  const titleFor = (id: string) =>
    opps.find((o) => o.id === id)?.title ?? id;

  return (
    <div className="flex flex-col gap-2 p-2">
      {apps.map((a) => (
        <div key={a.id} className="rounded border border-gray-200 p-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="font-medium">{titleFor(a.opportunity_id)}</span>
            <span className="rounded bg-gray-100 px-2 py-0.5 text-xs uppercase">
              {a.status}
            </span>
          </div>
          {a.submitted_at && (
            <div className="text-xs text-gray-500">
              submitted {new Date(a.submitted_at).toLocaleDateString()}
            </div>
          )}
          {a.portal_url && (
            <a
              href={a.portal_url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-blue-600 underline"
            >
              portal
            </a>
          )}
          {a.notes && <p className="mt-1 text-xs text-gray-600">{a.notes}</p>}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Wire the tab into `frontend/app/page.tsx`**

1. Add the import near the other component imports:
```tsx
import ApplicationsTab from "./components/ApplicationsTab";
```
2. Add `fetchApplications` and `Application` to the existing `@/lib/api` import.
3. Widen the tab state union and add applications state:
```tsx
  const [canvasTab, setCanvasTab] = useState<"workspace" | "profile" | "applications">("workspace");
  const [applications, setApplications] = useState<Application[]>([]);
```
4. In the canvas loader (the `Promise.all([... fetchOpportunities()])` block), also load applications — after the existing `setArtifacts(a)` etc., add:
```tsx
    fetchApplications().then(setApplications).catch(() => setApplications([]));
```
5. Add a third tab button beside the Profile button:
```tsx
            <button
              className={
                canvasTab === "applications"
                  ? "border-b-2 border-black px-3 py-2 text-sm font-medium"
                  : "px-3 py-2 text-sm text-gray-500"
              }
              onClick={() => setCanvasTab("applications")}
            >
              Applications ({applications.length})
            </button>
```
(Copy the exact className strings from the existing Profile button so styling matches.)
6. In the render switch, handle the new tab. Change the `canvasTab === "profile" ? <ProfileTab /> : (...)` expression so applications renders its tab, e.g.:
```tsx
          {canvasTab === "profile" ? (
            <ProfileTab />
          ) : canvasTab === "applications" ? (
            <ApplicationsTab />
          ) : (
            /* existing workspace block unchanged */
          )}
```

- [ ] **Step 4: Verify the frontend builds**

Run: `npm --prefix frontend run build`
Expected: build completes with no type errors (Next.js "Compiled successfully").

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/app/components/ApplicationsTab.tsx frontend/app/page.tsx
git commit -m "feat(ui): read-only Applications canvas tab"
```

---

## Final verification

- [ ] `.venv/bin/python -m pytest -q` → all pass.
- [ ] `scripts/ci/gate.sh` → GATE PASSED.
- [ ] `npm --prefix frontend run build` → Compiled successfully.
- [ ] `git log --oneline` shows 4 focused commits on `feature/application-tracking`.

## Self-Review (completed by plan author)

- **Spec coverage:** service `record_application`/`list_applications` (T1, spec §3); agent tool (T2, §4); API list + detail include (T3, §5); frontend type/fetch/tab (T4, §6); tests service/tool/API (T1–T3, §7); update-by-id semantics with create-fallback (T1, §3); no POST endpoint (T3, §5); writes via agent only (§2).
- **Placeholder scan:** none — every code step has concrete code; T4 build step is the explicit frontend check (the gate does not run `next build`).
- **Type consistency:** `record_application(...) -> Application` signature identical across T1 def, T2 tool call, T3 router. `ApplicationStatus` enum values match the model and the tool's JSON `enum`. `Application` TS type fields match the model's serialized columns. `fetchApplications` mirrors `fetchArtifacts`.
