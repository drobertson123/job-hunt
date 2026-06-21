# Weekly Process Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A deterministic weekly identify→apply→follow-up review service + API + UI that buckets the pipeline and one-click materializes the week's actions.

**Architecture:** `app/weekly_review.py` queries opportunities by `PipelineStage` into three buckets (+ interviews this week); `create_weekly_actions` idempotently creates per-bucket Action rows. A `/api/weekly-review` router and a `WeeklyTab` UI.

**Tech Stack:** Python 3.12, SQLModel/SQLite, FastAPI, Next.js/React/Tailwind, pytest.

## Global Constraints
- Buckets: identify=`new`; apply=`qualifying`,`analyzing` minus opps with an Application; follow_up=`active`,`in_dialogue`. `won`/`lost` excluded everywhere.
- `now` is injected (naive UTC, `app.models._utcnow`) for deterministic tests.
- `create_weekly_actions` creates `Action` rows DIRECTLY (not via `services.add_action`) so it does NOT bump `Opportunity.last_activity_at`. Idempotent: skip an item that already has an OPEN action of the matching kind.
- pytest interpreter: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest …`. Frontend: `npm --prefix frontend install` then `npm --prefix frontend run build`.
- Verification: `bash scripts/ci/gate.sh` GREEN; `npm --prefix frontend run build` succeeds.
- Do NOT invoke any finishing/branch skill — stop after committing and reporting.

---

### Task 1: Weekly-review service + API

**Files:**
- Create: `app/weekly_review.py`
- Create: `app/routers/weekly.py`
- Modify: `app/main.py` (include the router)
- Test: `tests/test_weekly_review.py`, `tests/test_weekly_api.py`

**Interfaces:**
- Produces: `weekly_review(session, *, now=None) -> dict`, `create_weekly_actions(session, *, now=None) -> dict`; `GET /api/weekly-review`, `POST /api/weekly-review/actions`.

- [ ] **Step 1: Write the failing service test**

Create `tests/test_weekly_review.py`:
```python
from datetime import datetime, timedelta

from sqlmodel import Session

from app.db import engine
from app import services, weekly_review as wr
from app.models import (
    Opportunity, OpportunityType, PipelineStage, Application, Action,
    ActionKind, ActionStatus,
)


def _opp(stage, title="O", type_=OpportunityType.job):
    with Session(engine) as s:
        o = Opportunity(type=type_, title=title, stage=stage)
        s.add(o)
        s.commit()
        s.refresh(o)
        return o


def test_weekly_review_buckets_by_stage():
    now = datetime(2026, 6, 21, 12, 0)
    n = _opp(PipelineStage.new, "New one")
    q = _opp(PipelineStage.qualifying, "Qualify me")
    a = _opp(PipelineStage.active, "Applied")
    won = _opp(PipelineStage.won, "Won")
    with Session(engine) as s:
        plan = wr.weekly_review(s, now=now)
    ids = lambda b: {x["id"] for x in plan[b]}
    assert n.id in ids("to_identify")
    assert q.id in ids("to_apply")
    assert a.id in ids("to_follow_up")
    assert won.id not in ids("to_identify") | ids("to_apply") | ids("to_follow_up")


def test_to_apply_excludes_opps_with_application():
    now = datetime(2026, 6, 21, 12, 0)
    q = _opp(PipelineStage.qualifying, "Has app")
    with Session(engine) as s:
        s.add(Application(opportunity_id=q.id))
        s.commit()
        plan = wr.weekly_review(s, now=now)
    assert q.id not in {x["id"] for x in plan["to_apply"]}


def test_interviews_this_week_window():
    now = datetime(2026, 6, 21, 12, 0)
    with Session(engine) as s:
        soon = services.add_interview(s, title="Soon", starts_at=now + timedelta(days=2))
        far = services.add_interview(s, title="Far", starts_at=now + timedelta(days=30))
        plan = wr.weekly_review(s, now=now)
    iids = {x["id"] for x in plan["interviews_this_week"]}
    assert soon.id in iids and far.id not in iids


def test_create_weekly_actions_idempotent_and_no_activity_bump():
    now = datetime(2026, 6, 21, 12, 0)
    q = _opp(PipelineStage.qualifying, "Apply target")
    with Session(engine) as s:
        before = s.get(Opportunity, q.id).last_activity_at
        r1 = wr.create_weekly_actions(s, now=now)
        assert r1["created"] >= 1
        # the apply action exists, open, correct kind/title
        act = s.exec(
            __import__("sqlmodel").select(Action).where(Action.opportunity_id == q.id)
        ).first()
        assert act.kind == ActionKind.apply and act.status == ActionStatus.open
        assert act.title.startswith("Apply:")
        # last_activity_at not bumped
        assert s.get(Opportunity, q.id).last_activity_at == before
    with Session(engine) as s:
        r2 = wr.create_weekly_actions(s, now=now)  # idempotent
        apply_actions = s.exec(
            __import__("sqlmodel").select(Action).where(
                Action.opportunity_id == q.id, Action.kind == ActionKind.apply
            )
        ).all()
        assert len(apply_actions) == 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_weekly_review.py -q`
Expected: FAIL (`ModuleNotFoundError: app.weekly_review`).

- [ ] **Step 3: Implement `app/weekly_review.py`**

```python
"""Weekly identify -> apply -> follow-up review over the pipeline (deterministic)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from app.models import (
    Action,
    ActionKind,
    ActionStatus,
    Application,
    InterviewEvent,
    Opportunity,
    PipelineStage,
    _utcnow,
)

IDENTIFY_STAGES = [PipelineStage.new]
APPLY_STAGES = [PipelineStage.qualifying, PipelineStage.analyzing]
FOLLOWUP_STAGES = [PipelineStage.active, PipelineStage.in_dialogue]


def _brief(o: Opportunity) -> dict[str, Any]:
    return {
        "id": o.id,
        "title": o.title,
        "organization": o.organization,
        "stage": o.stage.value,
        "type": o.type.value,
    }


def weekly_review(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or _utcnow()
    week_end = now + timedelta(days=7)

    identify = session.exec(
        select(Opportunity)
        .where(Opportunity.stage.in_(IDENTIFY_STAGES))
        .order_by(Opportunity.created_at.desc())
    ).all()

    applied_ids = set(session.exec(select(Application.opportunity_id)).all())
    apply_rows = session.exec(
        select(Opportunity)
        .where(Opportunity.stage.in_(APPLY_STAGES))
        .order_by(Opportunity.created_at.desc())
    ).all()
    to_apply = [o for o in apply_rows if o.id not in applied_ids]

    follow = session.exec(
        select(Opportunity)
        .where(Opportunity.stage.in_(FOLLOWUP_STAGES))
        .order_by(Opportunity.last_activity_at)
    ).all()

    interviews = session.exec(
        select(InterviewEvent)
        .where(InterviewEvent.starts_at >= now, InterviewEvent.starts_at <= week_end)
        .order_by(InterviewEvent.starts_at)
    ).all()

    return {
        "to_identify": [_brief(o) for o in identify],
        "to_apply": [_brief(o) for o in to_apply],
        "to_follow_up": [_brief(o) for o in follow],
        "interviews_this_week": [
            {
                "id": i.id,
                "title": i.title,
                "starts_at": i.starts_at.isoformat(),
                "opportunity_id": i.opportunity_id,
            }
            for i in interviews
        ],
        "counts": {
            "to_identify": len(identify),
            "to_apply": len(to_apply),
            "to_follow_up": len(follow),
            "interviews_this_week": len(interviews),
        },
    }


def create_weekly_actions(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    plan = weekly_review(session, now=now)
    specs = [
        ("to_identify", ActionKind.research, "Triage"),
        ("to_apply", ActionKind.apply, "Apply"),
        ("to_follow_up", ActionKind.followup, "Follow up"),
    ]
    created = 0
    for bucket, kind, verb in specs:
        for item in plan[bucket]:
            oid = item["id"]
            existing = session.exec(
                select(Action).where(
                    Action.opportunity_id == oid,
                    Action.kind == kind,
                    Action.status == ActionStatus.open,
                )
            ).first()
            if existing is not None:
                continue
            session.add(
                Action(title=f"{verb}: {item['title']}", opportunity_id=oid, kind=kind)
            )
            created += 1
    session.commit()
    return {"created": created}
```

- [ ] **Step 4: Run the service test to verify it passes**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_weekly_review.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing API test**

Create `tests/test_weekly_api.py`:
```python
def test_weekly_review_endpoint_shape(client):
    r = client.get("/api/weekly-review")
    assert r.status_code == 200
    body = r.json()
    for key in ("to_identify", "to_apply", "to_follow_up", "interviews_this_week", "counts"):
        assert key in body


def test_create_weekly_actions_endpoint(client):
    r = client.post("/api/weekly-review/actions")
    assert r.status_code == 200
    assert "created" in r.json()
```

- [ ] **Step 6: Implement the router + mount it**

Create `app/routers/weekly.py`:
```python
"""Weekly identify->apply->follow-up review endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import weekly_review
from app.db import get_session

router = APIRouter(prefix="/api/weekly-review", tags=["weekly-review"])


@router.get("")
def get_weekly_review(session: Session = Depends(get_session)) -> dict:
    return weekly_review.weekly_review(session)


@router.post("/actions")
def create_weekly_actions(session: Session = Depends(get_session)) -> dict:
    return weekly_review.create_weekly_actions(session)
```
In `app/main.py`: add `weekly` to the `from app.routers import (...)` block and `app.include_router(weekly.router)` with the others.

- [ ] **Step 7: Run the API test + full gate**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_weekly_api.py -q` → PASS
Then `bash scripts/ci/gate.sh` → GATE PASSED.

- [ ] **Step 8: Commit**

```bash
git add app/weekly_review.py app/routers/weekly.py app/main.py tests/test_weekly_review.py tests/test_weekly_api.py
git commit -m "feat(weekly): identify/apply/follow-up review service + API"
```

---

### Task 2: Frontend — This-week tab

**Files:**
- Modify: `frontend/lib/api.ts` (types + fetchers)
- Create: `frontend/app/components/WeeklyTab.tsx`
- Modify: `frontend/app/page.tsx` (canvas union, nav button, render branch)

**Interfaces:**
- Consumes: `/api/weekly-review` (GET) and `/api/weekly-review/actions` (POST).

- [ ] **Step 1: api.ts**

In `frontend/lib/api.ts`, add:
```ts
export type WeeklyOpp = {
  id: string;
  title: string;
  organization: string | null;
  stage: string;
  type: string;
};

export type WeeklyInterview = {
  id: number;
  title: string;
  starts_at: string;
  opportunity_id: string | null;
};

export type WeeklyReview = {
  to_identify: WeeklyOpp[];
  to_apply: WeeklyOpp[];
  to_follow_up: WeeklyOpp[];
  interviews_this_week: WeeklyInterview[];
  counts: Record<string, number>;
};

export async function fetchWeeklyReview(): Promise<WeeklyReview> {
  const res = await fetch("/api/weekly-review");
  if (!res.ok) throw new Error(`weekly review failed: ${res.status}`);
  return res.json();
}

export async function createWeeklyActions(): Promise<{ created: number }> {
  const res = await fetch("/api/weekly-review/actions", { method: "POST" });
  if (!res.ok) throw new Error(`create weekly actions failed: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Create `WeeklyTab.tsx`**

Model it on the existing tab idiom (read `frontend/app/components/ActionsTab.tsx` for `FetchError`, load pattern, Tailwind). Create `frontend/app/components/WeeklyTab.tsx`:
```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  WeeklyReview,
  WeeklyOpp,
  createWeeklyActions,
  fetchWeeklyReview,
} from "@/lib/api";
import FetchError from "./FetchError";

export default function WeeklyTab({ onOpen }: { onOpen: (oppId: string) => void }) {
  const [data, setData] = useState<WeeklyReview | null>(null);
  const [error, setError] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(() => {
    fetchWeeklyReview()
      .then((d) => {
        setData(d);
        setError(false);
      })
      .catch(() => {
        setData(null);
        setError(true);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const materialize = async () => {
    const r = await createWeeklyActions();
    setMsg(`${r.created} action${r.created === 1 ? "" : "s"} created`);
    load();
  };

  if (error) return <FetchError onRetry={load} />;
  if (!data) return <p className="p-4 text-sm text-slate-400">Loading…</p>;

  const bucket = (label: string, items: WeeklyOpp[]) => (
    <div className="rounded border border-slate-200 p-2">
      <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">
        {label} ({items.length})
      </h3>
      {items.length === 0 ? (
        <p className="text-xs text-slate-400">Nothing here.</p>
      ) : (
        <ul className="space-y-1">
          {items.map((o) => (
            <li
              key={o.id}
              onClick={() => onOpen(o.id)}
              className="cursor-pointer rounded px-1.5 py-1 text-sm hover:bg-slate-50"
            >
              <span className="font-medium">{o.title}</span>
              {o.organization && (
                <span className="text-slate-500"> · {o.organization}</span>
              )}
              <span className="ml-1 text-xs text-slate-400">[{o.stage}]</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  return (
    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 text-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">This week</h2>
        <div className="flex items-center gap-2">
          {msg && <span className="text-xs text-green-700">{msg}</span>}
          <button
            onClick={materialize}
            className="rounded bg-slate-900 px-3 py-1 text-xs text-white"
          >
            Create this week&apos;s actions
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {bucket("Identify", data.to_identify)}
        {bucket("Apply", data.to_apply)}
        {bucket("Follow up", data.to_follow_up)}
      </div>

      <div className="rounded border border-slate-200 p-2">
        <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">
          Interviews this week ({data.interviews_this_week.length})
        </h3>
        {data.interviews_this_week.length === 0 ? (
          <p className="text-xs text-slate-400">None scheduled.</p>
        ) : (
          <ul className="space-y-1">
            {data.interviews_this_week.map((iv) => (
              <li key={iv.id} className="text-sm">
                <span className="font-medium">{iv.title}</span>{" "}
                <span className="text-xs text-slate-500">
                  {new Date(iv.starts_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire into `page.tsx`**

Read `frontend/app/page.tsx`; mirror the existing `InterviewsTab` wiring:
1. `import WeeklyTab from "./components/WeeklyTab";`
2. Add `| "weekly"` to the `canvasTab` union.
3. Add a nav button labeled "This week" (same active-state classes as siblings; `onClick={() => setCanvasTab("weekly")}`).
4. Add a render branch `) : canvasTab === "weekly" ? ( <WeeklyTab onOpen={(id) => { setSelectedOpp(id); setCanvasTab("detail"); }} /> )` — match the exact `onOpen` handler the sibling tabs use.

- [ ] **Step 4: Build**

Run: `npm --prefix frontend install` (if needed) then `npm --prefix frontend run build` — must succeed.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/app/components/WeeklyTab.tsx frontend/app/page.tsx
git commit -m "feat(weekly): This-week tab — identify/apply/follow-up buckets + create actions"
```
