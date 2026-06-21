# Design: Action Lifecycle (snooze + reopen)

**Date:** 2026-06-20
**Status:** Approved (autonomous goal) — ready for implementation plan

## 1. Purpose

`ActionStatus` has `open/done/snoozed/canceled` but only `complete` (→done) is
wired. Add **snooze** (defer an open task out of the way) and **reopen**
(bring a done/snoozed task back to open) so the Actions tab is a real task
manager. The Attention tab already only surfaces `status==open` actions, so
snoozing an action removes it from "overdue" until reopened.

## 2. Scope

Backend: `snooze_action`/`reopen_action` services + `POST /api/actions/{id}/snooze`
and `/reopen`. Frontend: `snoozeAction`/`reopenAction` + Snooze/Reopen buttons in
the Actions tab. No schema change (reuses `ActionStatus`).

**Out of scope:** a snooze-until date (no `snooze_until` column — snooze is
indefinite until reopened); cancel; auto-resurface. Follows the existing
`complete_action`/`POST /{id}/complete` pattern.

## 3. Service — `app/services.py`

Mirror `complete_action`:

```python
def snooze_action(session: Session, action_id: int) -> Action | None:
    # set status = snoozed, updated_at = now; None if not found.

def reopen_action(session: Session, action_id: int) -> Action | None:
    # set status = open, clear completed_at, updated_at = now; None if not found.
```

## 4. API — `app/routers/actions.py`

Mirror the existing `complete_action` endpoint:
- `POST /api/actions/{action_id}/snooze` → `Action` (404 if missing).
- `POST /api/actions/{action_id}/reopen` → `Action` (404 if missing).

## 5. Frontend — `frontend/lib/api.ts` + `ActionsTab`

`api.ts`: `snoozeAction(id)` / `reopenAction(id)` (POST, mirror `completeAction`).

`ActionsTab` row buttons:
- `status === "open"` → existing **Done** button + a new **Snooze** button.
- `status !== "open"` (done/snoozed/canceled) → a **Reopen** button (replaces the
  current plain status text), plus keep showing the status label.
- After any of these → `load()` (reload the filtered list).

## 6. Testing

Backend test-first (`tests/test_action_lifecycle.py` or extend an existing
actions test): `snooze_action` sets snoozed; `reopen_action` sets open + clears
completed_at; both return None for a missing id; the two endpoints return the
updated row / 404. Frontend verified via `npm --prefix frontend run build`.

## 7. Notes

- No agent tool — snooze/reopen are human task-management actions (the agent
  creates/records actions via `record_action`); keeping them UI/API-only is
  intentional.
- Snooze is indefinite (no wake date); reopening is the way back. A future
  `snooze_until` column + auto-resurface is deferred.
