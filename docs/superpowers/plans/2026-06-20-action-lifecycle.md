# Action Lifecycle (snooze + reopen) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add snooze + reopen to actions — service, `POST /snooze`/`/reopen` endpoints, and Snooze/Reopen buttons in the Actions tab.

**Architecture:** Backend mirrors `complete_action`/`POST /{id}/complete`; frontend mirrors `completeAction` + the existing Done button. No schema change.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, pytest; Next.js/React/TypeScript.

## Global Constraints

- `snooze_action` sets `status=snoozed`; `reopen_action` sets `status=open` + clears `completed_at`; both set `updated_at`; both return `None` for a missing id (mirror `complete_action`).
- Endpoints mirror the existing `POST /api/actions/{id}/complete` (return the row, 404 if None).
- No agent tool (human task-management only). Backend test-first; frontend verified by `npm --prefix frontend run build`.
- Run backend tests with `.venv/bin/python -m pytest -q`.

---

### Task 1: Service — snooze_action + reopen_action

**Files:** Modify `app/services.py`; Test `tests/test_action_lifecycle.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_action_lifecycle.py
from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import Action, ActionStatus


def _action(s: Session) -> Action:
    a = Action(title="Task")
    s.add(a)
    s.commit()
    s.refresh(a)
    return a


def test_snooze_action():
    with Session(engine) as s:
        a = _action(s)
        out = services.snooze_action(s, a.id)
        assert out is not None and out.status == ActionStatus.snoozed


def test_reopen_action_clears_completed():
    with Session(engine) as s:
        a = _action(s)
        services.complete_action(s, a.id)
        out = services.reopen_action(s, a.id)
        assert out is not None and out.status == ActionStatus.open
        assert out.completed_at is None


def test_snooze_reopen_missing_returns_none():
    with Session(engine) as s:
        assert services.snooze_action(s, 999999) is None
        assert services.reopen_action(s, 999999) is None
```

- [ ] **Step 2: Run → fail** — `.venv/bin/python -m pytest tests/test_action_lifecycle.py -v` (AttributeError: snooze_action).

- [ ] **Step 3: Implement** — append to `app/services.py` (after `complete_action`):

```python
def snooze_action(session: Session, action_id: int) -> Action | None:
    action = session.get(Action, action_id)
    if action is None:
        return None
    action.status = ActionStatus.snoozed
    action.updated_at = _utcnow()
    session.add(action)
    session.commit()
    session.refresh(action)
    return action


def reopen_action(session: Session, action_id: int) -> Action | None:
    action = session.get(Action, action_id)
    if action is None:
        return None
    action.status = ActionStatus.open
    action.completed_at = None
    action.updated_at = _utcnow()
    session.add(action)
    session.commit()
    session.refresh(action)
    return action
```

- [ ] **Step 4: Run → pass** (3 tests).
- [ ] **Step 5: Commit** — `git add app/services.py tests/test_action_lifecycle.py && git commit -m "feat(services): snooze_action + reopen_action"`

---

### Task 2: API — /snooze + /reopen endpoints

**Files:** Modify `app/routers/actions.py`; Test `tests/test_action_lifecycle_api.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_action_lifecycle_api.py
from __future__ import annotations

from sqlmodel import Session

from app.db import engine
from app.models import Action


def _action_id() -> int:
    with Session(engine) as s:
        a = Action(title="Task")
        s.add(a)
        s.commit()
        s.refresh(a)
        return a.id


def test_snooze_then_reopen_endpoints(client):
    aid = _action_id()
    sn = client.post(f"/api/actions/{aid}/snooze")
    assert sn.status_code == 200 and sn.json()["status"] == "snoozed"
    ro = client.post(f"/api/actions/{aid}/reopen")
    assert ro.status_code == 200 and ro.json()["status"] == "open"


def test_snooze_missing_404(client):
    assert client.post("/api/actions/999999/snooze").status_code == 404
```

- [ ] **Step 2: Run → fail** — `.venv/bin/python -m pytest tests/test_action_lifecycle_api.py -v` (404 on snooze).

- [ ] **Step 3: Implement** — in `app/routers/actions.py`, after the `complete_action` endpoint, add:

```python
@router.post("/{action_id}/snooze")
def snooze_action(action_id: int, session: Session = Depends(get_session)) -> Action:
    action = services.snooze_action(session, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="action not found")
    return action


@router.post("/{action_id}/reopen")
def reopen_action(action_id: int, session: Session = Depends(get_session)) -> Action:
    action = services.reopen_action(session, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="action not found")
    return action
```

- [ ] **Step 4: Run new test, then full suite + gate** — `pytest tests/test_action_lifecycle_api.py -v`; `pytest -q`; `scripts/ci/gate.sh` (GATE PASSED).
- [ ] **Step 5: Commit** — `git add app/routers/actions.py tests/test_action_lifecycle_api.py && git commit -m "feat(api): action snooze + reopen endpoints"`

---

### Task 3: Frontend — fetchers + Snooze/Reopen buttons

**Files:** Modify `frontend/lib/api.ts`, `frontend/app/components/ActionsTab.tsx`.

- [ ] **Step 1: Add fetchers to `frontend/lib/api.ts`** (after `completeAction`):

```typescript
export async function snoozeAction(id: number): Promise<Action> {
  const res = await fetch(`/api/actions/${id}/snooze`, { method: "POST" });
  if (!res.ok) throw new Error(`snooze action failed: ${res.status}`);
  return res.json();
}

export async function reopenAction(id: number): Promise<Action> {
  const res = await fetch(`/api/actions/${id}/reopen`, { method: "POST" });
  if (!res.ok) throw new Error(`reopen action failed: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Wire the buttons in `frontend/app/components/ActionsTab.tsx`**

Read the file. Add `snoozeAction`/`reopenAction` to the `@/lib/api` import. The row currently ends with:
```tsx
              {a.status === "open" ? (
                <button onClick={() => completeAction(a.id).then(load)} ...>Done</button>
              ) : (
                <span className="text-xs text-slate-400">{a.status}</span>
              )}
```
Replace that block with: open → Done + Snooze; non-open → status label + Reopen:
```tsx
              {a.status === "open" ? (
                <>
                  <button
                    onClick={() => completeAction(a.id).then(load)}
                    className="rounded bg-slate-200 px-2 py-0.5 text-xs hover:bg-slate-300"
                  >
                    Done
                  </button>
                  <button
                    onClick={() => snoozeAction(a.id).then(load)}
                    className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-200"
                  >
                    Snooze
                  </button>
                </>
              ) : (
                <>
                  <span className="text-xs text-slate-400">{a.status}</span>
                  <button
                    onClick={() => reopenAction(a.id).then(load)}
                    className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-200"
                  >
                    Reopen
                  </button>
                </>
              )}
```
(Match the real surrounding markup — read it first.)

- [ ] **Step 3: Verify** — `npm --prefix frontend run build` (Compiled successfully); `pytest -q`; `scripts/ci/gate.sh`.
- [ ] **Step 4: Commit** — `git add frontend/lib/api.ts frontend/app/components/ActionsTab.tsx && git commit -m "feat(ui): Snooze + Reopen buttons in Actions tab"`

---

## Final verification
- [ ] `pytest -q` pass; `scripts/ci/gate.sh` PASSED; `npm --prefix frontend run build` OK; 3 commits on `feature/action-lifecycle`.

## Self-Review
- Spec coverage: snooze/reopen service (T1), endpoints (T2), fetchers + buttons (T3). Types: `snooze_action`/`reopen_action(session, action_id: int) -> Action | None` consistent across service/endpoint; `snoozeAction`/`reopenAction(id: number)` ↔ `Action.id`. No placeholders.
