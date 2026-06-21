# Interview Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add/remove interview calendar events tied to opportunities, with .ics export importable into any calendar.

**Architecture:** New `InterviewEvent` SQLModel table (auto-created by `create_all`), service CRUD, a stdlib `app/ics.py` iCalendar writer, an MCP `schedule_interview` agent tool, a `/api/interviews` router (CRUD + .ics), and an `InterviewsTab` UI.

**Tech Stack:** Python 3.12, SQLModel/SQLite, FastAPI, Next.js/React/Tailwind, pytest.

## Global Constraints
- Datetimes stored naive (matches existing `due_at`/`occurred_at`); the router strips tzinfo with `.replace(tzinfo=None)` like the actions router.
- .ics emits **floating** local time for `DTSTART`/`DTEND` (no `Z`) so user-entered wall-clock times display correctly in any viewer; `DTSTAMP` is UTC (`Z`). CRLF line endings; RFC 5545 escaping of `\ ; , \n`.
- All-upcoming export path is `/api/interviews/calendar.ics` (NOT `.ics` at the prefix root — avoids ambiguous routing); single is `/api/interviews/{id}.ics`.
- pytest interpreter: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest …` (worktree has no local .venv). Frontend: `npm --prefix frontend install` first (no node_modules), then `npm --prefix frontend run build`.
- Verification: `bash scripts/ci/gate.sh` GREEN and `npm --prefix frontend run build` succeeds.
- Do NOT invoke any finishing/branch skill — stop after committing and reporting.

---

### Task 1: Model, service, and .ics writer

**Files:**
- Modify: `app/models.py` (add `InterviewKind` + `InterviewEvent`)
- Modify: `app/services.py` (add interview CRUD)
- Create: `app/ics.py`
- Test: `tests/test_interviews_service.py`, `tests/test_ics.py`

**Interfaces:**
- Produces: `InterviewEvent`, `InterviewKind`; `services.add_interview/list_interviews/delete_interview`; `ics.to_ics(events, *, now)`.

- [ ] **Step 1: Write the model**

In `app/models.py`, after the `Communication` class, add:
```python
class InterviewKind(str, Enum):
    phone = "phone"
    video = "video"
    onsite = "onsite"
    technical = "technical"
    behavioral = "behavioral"
    final = "final"
    other = "other"


class InterviewEvent(SQLModel, table=True):
    __tablename__ = "interview_events"

    id: int | None = Field(default=None, primary_key=True)
    opportunity_id: str | None = Field(
        default=None, foreign_key="opportunities.id", index=True
    )
    title: str
    kind: InterviewKind = InterviewKind.other
    starts_at: datetime = Field(index=True)
    ends_at: datetime | None = None
    location: str = ""
    notes: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
```
(`Enum`, `Field`, `datetime`, `_utcnow`, `SQLModel` are already imported/defined in this file.)

- [ ] **Step 2: Write the service failing test**

Create `tests/test_interviews_service.py`:
```python
from datetime import datetime

from sqlmodel import Session

from app.db import engine
from app import services
from app.models import InterviewEvent, InterviewKind


def test_add_list_delete_interview_roundtrip():
    with Session(engine) as s:
        ev = services.add_interview(
            s, title="Phone screen", starts_at=datetime(2026, 7, 1, 14, 0),
            kind=InterviewKind.phone, location="Zoom", notes="bring questions",
        )
        assert ev.id is not None
        got = services.list_interviews(s)
        assert any(x.id == ev.id for x in got)
        assert services.delete_interview(s, ev.id) is True
        assert services.delete_interview(s, ev.id) is False
        assert all(x.id != ev.id for x in services.list_interviews(s))


def test_list_interviews_upcoming_and_order():
    with Session(engine) as s:
        past = services.add_interview(s, title="Past", starts_at=datetime(2000, 1, 1, 9, 0))
        soon = services.add_interview(s, title="Soon", starts_at=datetime(2999, 1, 1, 9, 0))
        later = services.add_interview(s, title="Later", starts_at=datetime(2999, 2, 1, 9, 0))
        upcoming = services.list_interviews(s, upcoming=True)
        ids = [x.id for x in upcoming]
        assert soon.id in ids and later.id in ids and past.id not in ids
        # ordered ascending by starts_at
        assert ids.index(soon.id) < ids.index(later.id)
```

- [ ] **Step 3: Run it to verify it fails**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_interviews_service.py -q`
Expected: FAIL (`AttributeError: module 'app.services' has no attribute 'add_interview'` / import error).

- [ ] **Step 4: Implement the service**

In `app/services.py`, add `InterviewEvent, InterviewKind` to the `from app.models import (...)` block, and add (near the actions section):
```python
def add_interview(
    session: Session,
    *,
    title: str,
    starts_at: datetime,
    opportunity_id: str | None = None,
    kind: InterviewKind = InterviewKind.other,
    ends_at: datetime | None = None,
    location: str = "",
    notes: str = "",
) -> InterviewEvent:
    ev = InterviewEvent(
        title=title,
        starts_at=starts_at,
        opportunity_id=opportunity_id,
        kind=kind,
        ends_at=ends_at,
        location=location,
        notes=notes,
    )
    session.add(ev)
    if opportunity_id:
        opp = session.get(Opportunity, opportunity_id)
        if opp:
            opp.last_activity_at = _utcnow()
            session.add(opp)
    session.commit()
    session.refresh(ev)
    return ev


def list_interviews(
    session: Session,
    *,
    opportunity_id: str | None = None,
    upcoming: bool = False,
) -> list[InterviewEvent]:
    stmt = select(InterviewEvent)
    if opportunity_id is not None:
        stmt = stmt.where(InterviewEvent.opportunity_id == opportunity_id)
    if upcoming:
        stmt = stmt.where(InterviewEvent.starts_at >= _utcnow())
    return list(session.exec(stmt.order_by(InterviewEvent.starts_at)).all())


def delete_interview(session: Session, interview_id: int) -> bool:
    ev = session.get(InterviewEvent, interview_id)
    if ev is None:
        return False
    session.delete(ev)
    session.commit()
    return True
```

- [ ] **Step 5: Run the service test to verify it passes**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_interviews_service.py -q`
Expected: PASS.

- [ ] **Step 6: Write the .ics failing test**

Create `tests/test_ics.py`:
```python
from datetime import datetime

from app.ics import to_ics
from app.models import InterviewEvent


def _ev(**kw):
    base = dict(id=1, title="Phone screen", starts_at=datetime(2026, 7, 1, 14, 0))
    base.update(kw)
    return InterviewEvent(**base)


def test_to_ics_basic_structure():
    now = datetime(2026, 6, 21, 12, 0)
    out = to_ics([_ev()], now=now)
    assert out.startswith("BEGIN:VCALENDAR")
    assert "END:VCALENDAR" in out
    assert "BEGIN:VEVENT" in out
    assert "UID:interview-1@opportunity-hunter" in out
    assert "DTSTART:20260701T140000" in out          # floating (no Z)
    assert "DTEND:20260701T150000" in out             # +1h default
    assert "DTSTAMP:20260621T120000Z" in out          # UTC stamp
    assert "\r\n" in out                              # CRLF


def test_to_ics_escapes_and_multiple_events():
    now = datetime(2026, 6, 21, 12, 0)
    out = to_ics(
        [_ev(id=1, title="Onsite, round 2; final"), _ev(id=2, title="Call")],
        now=now,
    )
    assert out.count("BEGIN:VEVENT") == 2
    assert "SUMMARY:Onsite\\, round 2\\; final" in out
```

- [ ] **Step 7: Run it to verify it fails**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_ics.py -q`
Expected: FAIL (`ModuleNotFoundError: app.ics`).

- [ ] **Step 8: Implement `app/ics.py`**

```python
"""Minimal RFC 5545 iCalendar writer for interview events (stdlib only).

ponytail: stored datetimes are naive wall-clock; DTSTART/DTEND are emitted as
*floating* local time (no Z) so a user-entered time shows at that clock time in
any viewer. DTSTAMP is UTC (Z), as the spec requires.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.models import InterviewEvent


def _esc(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _floating(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


def _stamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%SZ")


def _vevent(ev: InterviewEvent, *, now: datetime) -> list[str]:
    end = ev.ends_at or (ev.starts_at + timedelta(hours=1))
    lines = [
        "BEGIN:VEVENT",
        f"UID:interview-{ev.id}@opportunity-hunter",
        f"DTSTAMP:{_stamp(now)}",
        f"DTSTART:{_floating(ev.starts_at)}",
        f"DTEND:{_floating(end)}",
        f"SUMMARY:{_esc(ev.title)}",
    ]
    if ev.location:
        lines.append(f"LOCATION:{_esc(ev.location)}")
    if ev.notes:
        lines.append(f"DESCRIPTION:{_esc(ev.notes)}")
    lines.append("END:VEVENT")
    return lines


def to_ics(events: list[InterviewEvent], *, now: datetime) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Opportunity Hunter//Interviews//EN",
        "CALSCALE:GREGORIAN",
    ]
    for ev in events:
        lines.extend(_vevent(ev, now=now))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
```

- [ ] **Step 9: Run both test files to verify they pass**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_interviews_service.py tests/test_ics.py -q`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add app/models.py app/services.py app/ics.py tests/test_interviews_service.py tests/test_ics.py
git commit -m "feat(interviews): InterviewEvent model, service CRUD, and .ics writer"
```

---

### Task 2: Agent tool + API router

**Files:**
- Modify: `app/agent/tools.py` (add `schedule_interview` to `ALL_TOOLS`)
- Create: `app/routers/interviews.py`
- Modify: `app/main.py` (include the router)
- Test: `tests/test_interviews_api.py`

**Interfaces:**
- Consumes: `services.add_interview/list_interviews/delete_interview`, `ics.to_ics`.
- Produces: `mcp__app__schedule_interview`; `/api/interviews` CRUD + `.ics` endpoints.

- [ ] **Step 1: Add the agent tool**

In `app/agent/tools.py`: add `InterviewKind` to the `from app.models import (...)` block. Add this tool definition (next to `record_communication`):
```python
@tool(
    "schedule_interview",
    "Schedule an interview event for an opportunity (date/time, type, location/link).",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "starts_at": {"type": "string", "description": "ISO 8601 datetime"},
            "opportunity_id": {"type": "string"},
            "kind": {
                "type": "string",
                "enum": ["phone", "video", "onsite", "technical", "behavioral", "final", "other"],
            },
            "ends_at": {"type": "string", "description": "ISO 8601 datetime"},
            "location": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["title", "starts_at"],
    },
)
async def schedule_interview(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        starts = _parse_dt(args.get("starts_at"))
        if starts is None:
            return _ok("Could not schedule interview: starts_at (ISO 8601) is required.")
        ev = services.add_interview(
            s,
            title=args.get("title") or "Interview",
            starts_at=starts,
            opportunity_id=args.get("opportunity_id"),
            kind=_enum(InterviewKind, args.get("kind"), InterviewKind.other),
            ends_at=_parse_dt(args.get("ends_at")),
            location=args.get("location") or "",
            notes=args.get("notes") or "",
        )
        return _ok(f"Scheduled interview #{ev.id}: {ev.title!r} at {ev.starts_at.isoformat()}.")
```
Then add `schedule_interview` to the `ALL_TOOLS` list (e.g. after `record_communication`).

- [ ] **Step 2: Write the API failing test**

Create `tests/test_interviews_api.py`:
```python
def test_interview_crud_and_ics(client):
    # create
    r = client.post("/api/interviews", json={
        "title": "Tech screen", "starts_at": "2999-07-01T14:00:00",
        "kind": "technical", "location": "Zoom",
    })
    assert r.status_code == 200, r.text
    iv = r.json()
    iid = iv["id"]
    assert iv["kind"] == "technical"

    # list (upcoming)
    r = client.get("/api/interviews?upcoming=true")
    assert any(x["id"] == iid for x in r.json())

    # single .ics
    r = client.get(f"/api/interviews/{iid}.ics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    assert r.text.startswith("BEGIN:VCALENDAR")
    assert "BEGIN:VEVENT" in r.text

    # all-upcoming .ics
    r = client.get("/api/interviews/calendar.ics")
    assert r.status_code == 200
    assert "BEGIN:VCALENDAR" in r.text

    # delete
    assert client.delete(f"/api/interviews/{iid}").status_code == 204
    assert client.delete(f"/api/interviews/{iid}").status_code == 404


def test_interview_ics_unknown_404(client):
    assert client.get("/api/interviews/999999.ics").status_code == 404
```
(The `client` fixture exists in `tests/conftest.py` — used by other `*_api.py` tests.)

- [ ] **Step 3: Run it to verify it fails**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_interviews_api.py -q`
Expected: FAIL (router not mounted → 404).

- [ ] **Step 4: Implement the router**

Create `app/routers/interviews.py`:
```python
"""Interview calendar endpoints — CRUD + .ics export."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlmodel import Session

from app import services
from app.db import get_session
from app.ics import to_ics
from app.models import InterviewEvent, InterviewKind

router = APIRouter(prefix="/api/interviews", tags=["interviews"])


class InterviewCreate(BaseModel):
    title: str
    starts_at: datetime
    opportunity_id: str | None = None
    kind: InterviewKind = InterviewKind.other
    ends_at: datetime | None = None
    location: str = ""
    notes: str = ""


def _naive(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=None) if dt else None


def _ics_response(events: list[InterviewEvent], filename: str) -> Response:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return Response(
        content=to_ics(events, now=now),
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("")
def list_interviews(
    opportunity_id: str | None = None,
    upcoming: bool = False,
    session: Session = Depends(get_session),
) -> list[InterviewEvent]:
    return services.list_interviews(
        session, opportunity_id=opportunity_id, upcoming=upcoming
    )


@router.post("")
def create_interview(
    body: InterviewCreate, session: Session = Depends(get_session)
) -> InterviewEvent:
    return services.add_interview(
        session,
        title=body.title,
        starts_at=_naive(body.starts_at),
        opportunity_id=body.opportunity_id,
        kind=body.kind,
        ends_at=_naive(body.ends_at),
        location=body.location,
        notes=body.notes,
    )


@router.get("/calendar.ics")
def all_interviews_ics(session: Session = Depends(get_session)) -> Response:
    events = services.list_interviews(session, upcoming=True)
    return _ics_response(events, "interviews.ics")


@router.get("/{interview_id}.ics")
def interview_ics(
    interview_id: int, session: Session = Depends(get_session)
) -> Response:
    ev = session.get(InterviewEvent, interview_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="interview not found")
    return _ics_response([ev], f"interview-{interview_id}.ics")


@router.delete("/{interview_id}", status_code=204)
def delete_interview(
    interview_id: int, session: Session = Depends(get_session)
) -> Response:
    if not services.delete_interview(session, interview_id):
        raise HTTPException(status_code=404, detail="interview not found")
    return Response(status_code=204)
```
NOTE: define `/calendar.ics` BEFORE `/{interview_id}.ics` so the literal wins.

- [ ] **Step 5: Mount the router**

In `app/main.py`: add `interviews` to the `from app.routers import (...)` block and add `app.include_router(interviews.router)` with the others.

- [ ] **Step 6: Run the API test + full gate**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_interviews_api.py -q` → PASS
Then: `bash scripts/ci/gate.sh` → GATE PASSED.

- [ ] **Step 7: Commit**

```bash
git add app/agent/tools.py app/routers/interviews.py app/main.py tests/test_interviews_api.py
git commit -m "feat(interviews): schedule_interview tool + /api/interviews CRUD and .ics endpoints"
```

---

### Task 3: Frontend — InterviewsTab

**Files:**
- Modify: `frontend/lib/api.ts` (Interview type + fetchers)
- Create: `frontend/app/components/InterviewsTab.tsx`
- Modify: `frontend/app/page.tsx` (canvas union, nav button, render branch)

**Interfaces:**
- Consumes: `/api/interviews` endpoints.

- [ ] **Step 1: Add api.ts types + fetchers**

In `frontend/lib/api.ts`, add (near the actions/contacts section):
```ts
// ----- interviews (spec: interview-calendar) -----

export type Interview = {
  id: number;
  opportunity_id: string | null;
  title: string;
  kind: string;
  starts_at: string;
  ends_at: string | null;
  location: string;
  notes: string;
  created_at: string;
};

export async function fetchInterviews(upcoming = true): Promise<Interview[]> {
  const res = await fetch(`/api/interviews${upcoming ? "?upcoming=true" : ""}`);
  if (!res.ok) throw new Error(`interviews failed: ${res.status}`);
  return res.json();
}

export async function createInterview(body: {
  title: string;
  starts_at: string;
  opportunity_id?: string | null;
  kind?: string;
  location?: string;
  notes?: string;
}): Promise<Interview> {
  const res = await fetch("/api/interviews", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`create interview failed: ${res.status}`);
  return res.json();
}

export async function deleteInterview(id: number): Promise<void> {
  const res = await fetch(`/api/interviews/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`delete interview failed: ${res.status}`);
}
```

- [ ] **Step 2: Create `InterviewsTab.tsx`**

Model it on `frontend/app/components/ActionsTab.tsx` (read that file for the exact list/add/Tailwind idiom). Create `frontend/app/components/InterviewsTab.tsx`:
```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Interview,
  Opportunity,
  createInterview,
  deleteInterview,
  fetchInterviews,
  fetchOpportunities,
} from "@/lib/api";
import FetchError from "./FetchError";

const KINDS = ["phone", "video", "onsite", "technical", "behavioral", "final", "other"];

export default function InterviewsTab({ onOpen }: { onOpen: (oppId: string) => void }) {
  const [items, setItems] = useState<Interview[]>([]);
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("phone");
  const [startsAt, setStartsAt] = useState("");
  const [location, setLocation] = useState("");
  const [oppId, setOppId] = useState("");
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    fetchInterviews(true)
      .then((x) => {
        setItems(x);
        setError(false);
      })
      .catch(() => {
        setItems([]);
        setError(true);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    fetchOpportunities().then(setOpps).catch(() => setOpps([]));
  }, []);

  const submit = async () => {
    if (!title.trim() || !startsAt) return;
    await createInterview({
      title: title.trim(),
      starts_at: startsAt,
      kind,
      location: location.trim(),
      opportunity_id: oppId || null,
    });
    setTitle("");
    setStartsAt("");
    setLocation("");
    setOppId("");
    setKind("phone");
    load();
  };

  const titleFor = (id: string | null) =>
    id ? opps.find((o) => o.id === id)?.title ?? id : null;

  if (error) return <FetchError onRetry={load} />;

  return (
    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 text-sm">
      <div className="flex flex-wrap items-center gap-2 rounded border border-slate-200 p-2">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Interview title…"
          className="flex-1 rounded border px-2 py-1 text-sm"
        />
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          className="rounded border px-1 py-1 text-xs"
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <input
          type="datetime-local"
          value={startsAt}
          onChange={(e) => setStartsAt(e.target.value)}
          className="rounded border px-1 py-1 text-xs"
        />
        <input
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          placeholder="Location / link"
          className="rounded border px-2 py-1 text-xs"
        />
        <select
          value={oppId}
          onChange={(e) => setOppId(e.target.value)}
          className="rounded border px-1 py-1 text-xs"
        >
          <option value="">— no opportunity —</option>
          {opps.map((o) => (
            <option key={o.id} value={o.id}>
              {o.title}
            </option>
          ))}
        </select>
        <button
          onClick={submit}
          disabled={!title.trim() || !startsAt}
          className="rounded bg-slate-900 px-3 py-1 text-xs text-white disabled:opacity-50"
        >
          Add
        </button>
      </div>

      <div className="flex justify-end">
        <a
          href="/api/interviews/calendar.ics"
          className="rounded bg-slate-100 px-2 py-1 text-xs text-slate-700 hover:bg-slate-200"
        >
          Download all (.ics)
        </a>
      </div>

      {items.length === 0 ? (
        <p className="text-slate-400">No upcoming interviews.</p>
      ) : (
        items.map((iv) => {
          const t = titleFor(iv.opportunity_id);
          return (
            <div
              key={iv.id}
              className="flex items-center gap-2 rounded border border-slate-200 p-2"
            >
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs uppercase text-slate-600">
                {iv.kind}
              </span>
              <span className="flex-1">{iv.title}</span>
              {iv.location && (
                <span className="text-xs text-slate-500">{iv.location}</span>
              )}
              {t && (
                <span
                  onClick={() => onOpen(iv.opportunity_id as string)}
                  className="cursor-pointer text-xs text-blue-600 hover:underline"
                >
                  {t}
                </span>
              )}
              <span className="text-xs text-slate-500">
                {new Date(iv.starts_at).toLocaleString()}
              </span>
              <a
                href={`/api/interviews/${iv.id}.ics`}
                className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700 hover:bg-slate-200"
              >
                Add to calendar
              </a>
              <button
                onClick={() => deleteInterview(iv.id).then(load)}
                className="rounded bg-slate-200 px-2 py-0.5 text-xs hover:bg-slate-300"
              >
                Remove
              </button>
            </div>
          );
        })
      )}
    </div>
  );
}
```

- [ ] **Step 3: Wire into `page.tsx`**

Read `frontend/app/page.tsx` and follow the existing `ActionsTab` wiring pattern exactly:
1. `import InterviewsTab from "./components/InterviewsTab";`
2. Add `| "interviews"` to the `canvasTab` union type.
3. Add a nav button for interviews (copy the `actions` button block; label "Interviews", `onClick={() => setCanvasTab("interviews")}`, with the same active-state classes).
4. Add a render branch: `) : canvasTab === "interviews" ? (` `<InterviewsTab onOpen={(id) => { setSelectedOpp(id); setCanvasTab("detail"); }} />` — match how `ActionsTab`'s `onOpen` is wired in the existing file (use the same handler the actions branch uses to open an opportunity in the detail tab).

- [ ] **Step 4: Build**

Run: `npm --prefix frontend install` (if node_modules missing) then `npm --prefix frontend run build`
Expected: build succeeds (type-checks, regenerates `frontend/out`).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/app/components/InterviewsTab.tsx frontend/app/page.tsx
git commit -m "feat(interviews): InterviewsTab UI with add/remove and .ics download"
```
