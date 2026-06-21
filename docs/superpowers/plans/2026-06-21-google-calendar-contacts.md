# Google Calendar + Contacts Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the existing Google OAuth foundation, push interviews to Google Calendar and sync Contacts both ways.

**Architecture:** Expand OAuth scopes once; `gcal_service.py` / `gcontacts_service.py` use a single injectable `request(method,url,token,*,json,params)` seam; new id columns (`InterviewEvent.gcal_event_id`, `Contact.google_resource_name`, `Contact.email`); endpoints on the google router; minimal UI buttons.

**Tech Stack:** FastAPI, SQLModel/SQLite, httpx, Next.js/Tailwind, pytest.

## Global Constraints
- All Google HTTP via the injectable `request` (default thin `httpx.request` wrapper, `raise_for_status`, returns `{}` on empty body). Tests pass a fake; no network.
- Reuse `go.get_access_token` for auth. Datetimes naive-UTC; Calendar events sent as `{dateTime: <naive-iso>, timeZone: "UTC"}`.
- Contacts written through the service layer / model; dedup on `google_resource_name`.
- pytest: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest …`. Frontend: `npm --prefix frontend install` then build. Verify: `bash scripts/ci/gate.sh` GREEN + frontend build.
- Do NOT invoke any finishing/branch skill — stop after committing and reporting.

---

### Task 1: Scopes + Google Calendar push (`gcal_service.py`)

**Files:**
- Modify: `app/google_oauth.py` (DEFAULT_SCOPES)
- Modify: `app/models.py` (`InterviewEvent.gcal_event_id`), `app/db.py` (`_ensure_column`)
- Create: `app/gcal_service.py`
- Test: `tests/test_gcal_service.py`

- [ ] **Step 1: Expand scopes + add the column**

In `app/google_oauth.py`, set `DEFAULT_SCOPES` to:
```python
DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/contacts",
    "https://www.googleapis.com/auth/userinfo.email",
]
```
In `app/models.py`, in `class InterviewEvent`, after `notes: str = ""`, add:
```python
    gcal_event_id: str | None = Field(default=None, index=True)
```
In `app/db.py` `init_db`, after the existing `_ensure_column(...)` lines:
```python
    _ensure_column(engine, "interview_events", "gcal_event_id", "VARCHAR")
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_gcal_service.py`:
```python
from datetime import datetime, timedelta

from sqlmodel import Session

from app.db import engine
from app import services, gcal_service as gc
from app.models import InterviewKind


def _fake_request(log):
    def req(method, url, access_token, *, json=None, params=None):
        log.append((method, url, json))
        if method == "POST":
            return {"id": "evt-123"}
        return {}
    return req


def test_event_body_shape():
    iv = type("I", (), {})()
    iv.title = "Onsite"; iv.location = "HQ"; iv.notes = "bring laptop"
    iv.starts_at = datetime(2026, 7, 1, 14, 0); iv.ends_at = None
    iv.gcal_event_id = None
    body = gc.event_body(iv)
    assert body["summary"] == "Onsite"
    assert body["start"] == {"dateTime": "2026-07-01T14:00:00", "timeZone": "UTC"}
    assert body["end"] == {"dateTime": "2026-07-01T15:00:00", "timeZone": "UTC"}  # +1h
    assert body["location"] == "HQ" and body["description"] == "bring laptop"


def test_push_interview_creates_then_updates():
    log = []
    with Session(engine) as s:
        iv = services.add_interview(s, title="Call", starts_at=datetime(2999, 1, 1, 9, 0), kind=InterviewKind.phone)
        eid = gc.push_interview(s, iv, access_token="AT", request=_fake_request(log))
        assert eid == "evt-123" and iv.gcal_event_id == "evt-123"
        assert log[0][0] == "POST"
        # second push → PATCH (already linked)
        log2 = []
        gc.push_interview(s, iv, access_token="AT", request=_fake_request(log2))
        assert log2[0][0] == "PATCH" and "evt-123" in log2[0][1]


def test_sync_upcoming_counts():
    log = []
    with Session(engine) as s:
        services.add_interview(s, title="A", starts_at=datetime(2999, 1, 1, 9, 0))
        services.add_interview(s, title="B", starts_at=datetime(2999, 2, 1, 9, 0))
        services.add_interview(s, title="Past", starts_at=datetime(2000, 1, 1, 9, 0))
        r = gc.sync_upcoming(s, access_token="AT", request=_fake_request(log), now=datetime(2026, 6, 21, 12, 0))
    assert r == {"pushed": 2, "updated": 0}


def test_delete_event_swallows_errors():
    def boom(*a, **k):
        raise RuntimeError("404")
    gc.delete_event("AT", "evt-x", request=boom)  # must not raise
```

- [ ] **Step 3: Run it → fail** (`ModuleNotFoundError: app.gcal_service`).

- [ ] **Step 4: Implement `app/gcal_service.py`**

```python
"""Push interview events to Google Calendar (injectable HTTP for tests)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

import httpx
from sqlmodel import Session, select

from app.models import InterviewEvent, _utcnow

EVENTS_URI = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

Request = Callable[..., dict[str, Any]]


def _request(method: str, url: str, access_token: str, *, json: Any = None, params: Any = None) -> dict[str, Any]:
    r = httpx.request(method, url, headers={"Authorization": f"Bearer {access_token}"}, json=json, params=params, timeout=30)
    r.raise_for_status()
    return r.json() if r.content else {}


def event_body(iv: InterviewEvent) -> dict[str, Any]:
    end = iv.ends_at or (iv.starts_at + timedelta(hours=1))
    body: dict[str, Any] = {
        "summary": iv.title,
        "start": {"dateTime": iv.starts_at.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
    }
    if iv.location:
        body["location"] = iv.location
    if iv.notes:
        body["description"] = iv.notes
    return body


def push_interview(session: Session, iv: InterviewEvent, *, access_token: str, request: Request = _request) -> str | None:
    body = event_body(iv)
    if iv.gcal_event_id:
        request("PATCH", f"{EVENTS_URI}/{iv.gcal_event_id}", access_token, json=body)
        return iv.gcal_event_id
    resp = request("POST", EVENTS_URI, access_token, json=body)
    iv.gcal_event_id = resp.get("id")
    session.add(iv)
    session.commit()
    session.refresh(iv)
    return iv.gcal_event_id


def delete_event(access_token: str, event_id: str, *, request: Request = _request) -> None:
    try:
        request("DELETE", f"{EVENTS_URI}/{event_id}", access_token)
    except Exception:  # noqa: BLE001 — already-deleted is fine
        pass


def sync_upcoming(session: Session, *, access_token: str, request: Request = _request, now: datetime | None = None) -> dict[str, int]:
    now = now or _utcnow()
    rows = session.exec(select(InterviewEvent).where(InterviewEvent.starts_at >= now)).all()
    pushed = updated = 0
    for iv in rows:
        had = bool(iv.gcal_event_id)
        push_interview(session, iv, access_token=access_token, request=request)
        if had:
            updated += 1
        else:
            pushed += 1
    return {"pushed": pushed, "updated": updated}
```

- [ ] **Step 5: Run the test → pass.** Run: `… pytest tests/test_gcal_service.py -q`

- [ ] **Step 6: Commit**

```bash
git add app/google_oauth.py app/models.py app/db.py app/gcal_service.py tests/test_gcal_service.py
git commit -m "feat(google): calendar scopes + push interviews to Google Calendar"
```

---

### Task 2: Google Contacts sync (`gcontacts_service.py`)

**Files:**
- Modify: `app/models.py` (`Contact.google_resource_name`, `Contact.email`), `app/db.py` (`_ensure_column` ×2)
- Modify: `app/services.py` (`add_contact` gains `email`)
- Create: `app/gcontacts_service.py`
- Test: `tests/test_gcontacts_service.py`

- [ ] **Step 1: Columns + service param**

In `app/models.py`, in `class Contact`, after `link: str | None = None`, add:
```python
    email: str | None = None
    google_resource_name: str | None = Field(default=None, index=True)
```
In `app/db.py` `init_db`:
```python
    _ensure_column(engine, "contacts", "email", "VARCHAR")
    _ensure_column(engine, "contacts", "google_resource_name", "VARCHAR")
```
In `app/services.py` `add_contact`, add a param `email: str | None = None` (after `organization`) and set `email=email` in the `Contact(...)` constructor.

- [ ] **Step 2: Write the failing test**

Create `tests/test_gcontacts_service.py`:
```python
from sqlmodel import Session, select

from app.db import engine
from app import gcontacts_service as gco, services
from app.models import Contact


def _import_request(people):
    def req(method, url, access_token, *, json=None, params=None):
        return {"connections": people}
    return req


def test_import_contacts_upserts_and_dedupes():
    people = [
        {"resourceName": "people/c1", "names": [{"displayName": "Sarah Lee"}],
         "emailAddresses": [{"value": "sarah@kore1.com"}],
         "organizations": [{"name": "KORE1"}]},
        {"resourceName": "people/c2", "names": [{"displayName": "No Email"}]},
        {"resourceName": "people/c3"},  # no name → skipped
    ]
    with Session(engine) as s:
        r1 = gco.import_contacts(s, access_token="AT", request=_import_request(people))
        assert r1 == {"imported": 2, "skipped": 1}
        rows = s.exec(select(Contact)).all()
        sarah = next(c for c in rows if c.name == "Sarah Lee")
        assert sarah.email == "sarah@kore1.com" and sarah.organization == "KORE1"
        assert sarah.google_resource_name == "people/c1"
        # re-import dedupes on resourceName
        r2 = gco.import_contacts(s, access_token="AT", request=_import_request(people))
        assert r2["imported"] == 0


def test_push_contact_creates_then_updates():
    log = []

    def req(method, url, access_token, *, json=None, params=None):
        log.append((method, url))
        if method == "POST":
            return {"resourceName": "people/new1"}
        return {}

    with Session(engine) as s:
        c = services.add_contact(s, name="Bob Roe", email="bob@x.com", organization="Acme")
        rn = gco.push_contact(s, c, access_token="AT", request=req)
        assert rn == "people/new1" and c.google_resource_name == "people/new1"
        assert log[0][0] == "POST"
        log2_len = len(log)
        gco.push_contact(s, c, access_token="AT", request=req)  # linked → PATCH
        assert log[log2_len][0] == "PATCH"
```

- [ ] **Step 3: Run it → fail.**

- [ ] **Step 4: Implement `app/gcontacts_service.py`**

```python
"""Sync Google Contacts <-> app Contacts (injectable HTTP for tests).

ponytail: People `updateContact` strictly needs the current etag; the PATCH path
here is best-effort (create is the primary use). Live-verify update separately.
"""

from __future__ import annotations

from typing import Any, Callable

import httpx
from sqlmodel import Session, select

from app.models import Contact

CONNECTIONS_URI = "https://people.googleapis.com/v1/people/me/connections"
CREATE_URI = "https://people.googleapis.com/v1/people:createContact"
PERSON_FIELDS = "names,emailAddresses,organizations"

Request = Callable[..., dict[str, Any]]


def _request(method: str, url: str, access_token: str, *, json: Any = None, params: Any = None) -> dict[str, Any]:
    r = httpx.request(method, url, headers={"Authorization": f"Bearer {access_token}"}, json=json, params=params, timeout=30)
    r.raise_for_status()
    return r.json() if r.content else {}


def _first(person: dict, key: str, field: str) -> str | None:
    items = person.get(key) or []
    return items[0].get(field) if items else None


def import_contacts(session: Session, *, access_token: str, request: Request = _request, page_size: int = 200) -> dict[str, int]:
    resp = request("GET", CONNECTIONS_URI, access_token, params={"personFields": PERSON_FIELDS, "pageSize": page_size})
    imported = skipped = 0
    for person in resp.get("connections", []):
        name = _first(person, "names", "displayName")
        rn = person.get("resourceName")
        if not name:
            skipped += 1
            continue
        if rn and session.exec(select(Contact).where(Contact.google_resource_name == rn)).first():
            skipped += 1
            continue
        session.add(
            Contact(
                name=name,
                email=_first(person, "emailAddresses", "value"),
                organization=_first(person, "organizations", "name"),
                google_resource_name=rn,
            )
        )
        imported += 1
    session.commit()
    return {"imported": imported, "skipped": skipped}


def push_contact(session: Session, contact: Contact, *, access_token: str, request: Request = _request) -> str | None:
    body: dict[str, Any] = {"names": [{"givenName": contact.name}]}
    if contact.email:
        body["emailAddresses"] = [{"value": contact.email}]
    if contact.organization:
        body["organizations"] = [{"name": contact.organization}]
    if contact.google_resource_name:
        request(
            "PATCH",
            f"https://people.googleapis.com/v1/{contact.google_resource_name}:updateContact",
            access_token,
            json=body,
            params={"updatePersonFields": PERSON_FIELDS},
        )
        return contact.google_resource_name
    resp = request("POST", CREATE_URI, access_token, json=body)
    contact.google_resource_name = resp.get("resourceName")
    session.add(contact)
    session.commit()
    session.refresh(contact)
    return contact.google_resource_name
```

- [ ] **Step 5: Run the test + full gate** → PASS / GATE PASSED.

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/db.py app/services.py app/gcontacts_service.py tests/test_gcontacts_service.py
git commit -m "feat(google): Google Contacts import + push (dedup on resourceName)"
```

---

### Task 3: Endpoints, interview-delete hook, and UI

**Files:**
- Modify: `app/routers/google.py` (calendar/contacts endpoints)
- Modify: `app/routers/interviews.py` (delete also removes the Google event)
- Modify: `frontend/lib/api.ts` + `frontend/app/components/InterviewsTab.tsx` (Sync to Google Calendar) + Settings/contacts UI (Import Google contacts)
- Test: extend `tests/test_google_api.py`

- [ ] **Step 1: Endpoints**

In `app/routers/google.py`, add (import `gcal_service`, `gcontacts_service`, and `Contact` + `select`/`Session` as needed):
```python
@router.post("/calendar/sync")
def calendar_sync(session: Session = Depends(get_session)) -> dict:
    token = go.get_access_token(session, now=_utcnow())
    return gcal_service.sync_upcoming(session, access_token=token)


@router.post("/contacts/import")
def contacts_import(session: Session = Depends(get_session)) -> dict:
    token = go.get_access_token(session, now=_utcnow())
    return gcontacts_service.import_contacts(session, access_token=token)


@router.post("/contacts/{contact_id}/push")
def contact_push(contact_id: int, session: Session = Depends(get_session)) -> dict:
    from app.models import Contact

    contact = session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="contact not found")
    token = go.get_access_token(session, now=_utcnow())
    rn = gcontacts_service.push_contact(session, contact, access_token=token)
    return {"resource_name": rn}
```

- [ ] **Step 2: Interview delete also removes the Google event**

In `app/routers/interviews.py` `delete_interview`: before deleting the row, capture it; after a successful delete, if it had a `gcal_event_id` and Google is connected, best-effort remove it. Concretely, fetch the row first:
```python
    ev = session.get(InterviewEvent, interview_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="interview not found")
    gcal_id = ev.gcal_event_id
    if not services.delete_interview(session, interview_id):
        raise HTTPException(status_code=404, detail="interview not found")
    if gcal_id:
        from app import google_oauth as go, gcal_service
        from app.models import _utcnow
        try:
            if go.status(session).get("connected"):
                gcal_service.delete_event(go.get_access_token(session, now=_utcnow()), gcal_id)
        except Exception:  # noqa: BLE001 — google cleanup is best-effort
            pass
    return Response(status_code=204)
```
(Add `from app.models import InterviewEvent` to the imports if not present.)

- [ ] **Step 3: Failing endpoint tests (append to `tests/test_google_api.py`)**

```python
def test_calendar_sync_endpoint(client, monkeypatch):
    import app.routers.google as mod
    monkeypatch.setattr(mod.go, "get_access_token", lambda session, now: "AT")
    monkeypatch.setattr(mod.gcal_service, "sync_upcoming", lambda session, **kw: {"pushed": 2, "updated": 0})
    r = client.post("/api/google/calendar/sync")
    assert r.status_code == 200 and r.json()["pushed"] == 2


def test_contacts_import_endpoint(client, monkeypatch):
    import app.routers.google as mod
    monkeypatch.setattr(mod.go, "get_access_token", lambda session, now: "AT")
    monkeypatch.setattr(mod.gcontacts_service, "import_contacts", lambda session, **kw: {"imported": 3, "skipped": 1})
    r = client.post("/api/google/contacts/import")
    assert r.status_code == 200 and r.json()["imported"] == 3


def test_contact_push_404(client):
    assert client.post("/api/google/contacts/999999/push").status_code in (401, 404)
```
(Note: `/contacts/999999/push` first hits `session.get(Contact, …)` → None → 404 before the token call, so 404 is expected; allow 401 in case ordering differs.)

- [ ] **Step 4: Run backend tests + gate** → PASS / GATE PASSED.

- [ ] **Step 5: UI (minimal)**

- `frontend/lib/api.ts`: add `syncGoogleCalendar()` → POST `/api/google/calendar/sync`; `importGoogleContacts()` → POST `/api/google/contacts/import`.
- `InterviewsTab.tsx`: add a **Sync to Google Calendar** button next to "Download all (.ics)" that calls `syncGoogleCalendar()` and shows `{pushed} pushed`. Match existing button styling (TwinForge tokens: `Button` primitive or `rounded-sm border border-line …`).
- `SettingsBadge.tsx`: under the Google block (when connected), add an **Import Google contacts** button calling `importGoogleContacts()` showing `{imported} imported`.
Run: `npm --prefix frontend install` then `npm --prefix frontend run build` → succeeds.

- [ ] **Step 6: Commit**

```bash
git add app/routers/google.py app/routers/interviews.py frontend/lib/api.ts frontend/app/components/InterviewsTab.tsx frontend/app/components/SettingsBadge.tsx tests/test_google_api.py
git commit -m "feat(google): calendar/contacts endpoints + interview-delete cleanup + sync UI"
```
