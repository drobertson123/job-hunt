# Google OAuth + Gmail Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OAuth2 foundation for Google + a Gmail connector that ingests messages into Communications.

**Architecture:** `google_oauth.py` (pure helpers + injectable `poster`/`getter`); tokens/creds in the `settings` key/value table; `gmail_service.py` (injectable `fetcher`) maps messages → Communications deduped on a new `Communication.external_id`; `routers/google.py` exposes status/connect/callback/sync; minimal Settings UI + setup guide.

**Tech Stack:** FastAPI, SQLModel/SQLite, httpx, Next.js/Tailwind, pytest.

## Global Constraints
- ALL Google HTTP goes through injectable callables (`poster`, `getter`, `fetcher`) that default to thin `httpx` wrappers — tests never hit the network.
- Datetimes naive UTC (`app.models._utcnow`); OAuth expiry math uses the injected `now` consistently (never mix tz-aware/naive).
- Secrets (client secret, tokens) are stored in `settings` and NEVER returned by any GET (report booleans only).
- Gmail writes go through `record_communication` (Constitution II); dedup on `external_id`.
- pytest: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest …`. Frontend: `npm --prefix frontend install` then build. Verify: `bash scripts/ci/gate.sh` GREEN + frontend build.
- Do NOT invoke any finishing/branch skill — stop after committing and reporting.

---

### Task 1: OAuth foundation (`google_oauth.py` + settings keys)

**Files:**
- Modify: `app/settings_service.py` (Google keys + resolver)
- Create: `app/google_oauth.py`
- Test: `tests/test_google_oauth.py`

- [ ] **Step 1: Settings keys**

In `app/settings_service.py`, add after the existing key constants:
```python
GOOGLE_CLIENT_ID = "google_client_id"
GOOGLE_CLIENT_SECRET = "google_client_secret"
GOOGLE_OAUTH_TOKEN = "google_oauth_token"  # JSON blob
GOOGLE_OAUTH_STATE = "google_oauth_state"
```
and a resolver:
```python
def resolve_google_client(session: Session) -> tuple[str | None, str | None]:
    return (get_setting(session, GOOGLE_CLIENT_ID), get_setting(session, GOOGLE_CLIENT_SECRET))
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_google_oauth.py`:
```python
from datetime import datetime, timedelta

import pytest
from sqlmodel import Session

from app.db import engine
from app import google_oauth as go, settings_service as ss


def _set_client():
    with Session(engine) as s:
        ss.set_setting(s, ss.GOOGLE_CLIENT_ID, "cid")
        ss.set_setting(s, ss.GOOGLE_CLIENT_SECRET, "secret")


def test_build_auth_url_has_required_params():
    url = go.build_auth_url(client_id="cid", redirect_uri="http://127.0.0.1:8000/cb", state="xyz")
    assert url.startswith(go.AUTH_URI)
    for frag in ["client_id=cid", "access_type=offline", "state=xyz", "response_type=code", "gmail.readonly"]:
        assert frag in url


def test_exchange_code_builds_token():
    now = datetime(2026, 6, 21, 12, 0)
    captured = {}

    def poster(url, data):
        captured["url"] = url
        captured["data"] = data
        return {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600, "scope": "s"}

    tok = go.exchange_code(client_id="cid", client_secret="secret", code="C", redirect_uri="R", now=now, poster=poster)
    assert captured["url"] == go.TOKEN_URI
    assert captured["data"]["grant_type"] == "authorization_code"
    assert tok["access_token"] == "AT" and tok["refresh_token"] == "RT"
    assert tok["expiry"] == (now + timedelta(seconds=3600)).isoformat()


def test_get_access_token_returns_fresh_then_refreshes():
    _set_client()
    now = datetime(2026, 6, 21, 12, 0)
    with Session(engine) as s:
        # store a token that is still valid
        go.save_token(s, {"access_token": "AT1", "refresh_token": "RT", "scope": "s",
                          "expiry": (now + timedelta(hours=1)).isoformat()})
        assert go.get_access_token(s, now=now, poster=lambda u, d: {}) == "AT1"

        # store an EXPIRED token → refresh path
        go.save_token(s, {"access_token": "OLD", "refresh_token": "RT", "scope": "s",
                          "expiry": (now - timedelta(minutes=5)).isoformat()})

        def poster(url, data):
            assert data["grant_type"] == "refresh_token"
            return {"access_token": "AT2", "expires_in": 3600, "scope": "s"}

        assert go.get_access_token(s, now=now, poster=poster) == "AT2"
        # refresh_token preserved across the refresh (response omitted it)
        assert go.load_token(s)["refresh_token"] == "RT"


def test_get_access_token_raises_when_not_connected():
    with Session(engine) as s:
        ss.set_setting(s, ss.GOOGLE_OAUTH_TOKEN, "")  # ensure cleared
        with pytest.raises(RuntimeError):
            go.get_access_token(s, now=datetime(2026, 6, 21, 12, 0), poster=lambda u, d: {})


def test_status_shapes():
    _set_client()
    now = datetime(2026, 6, 21, 12, 0)
    with Session(engine) as s:
        go.save_token(s, {"access_token": "AT", "refresh_token": "RT", "scope": "x",
                          "expiry": (now + timedelta(hours=1)).isoformat()}, email="me@x.com")
        st = go.status(s)
    assert st["credentials_configured"] and st["connected"] and st["email"] == "me@x.com"
```

- [ ] **Step 3: Run it to verify it fails**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_google_oauth.py -q`
Expected: FAIL (`ModuleNotFoundError: app.google_oauth`).

- [ ] **Step 4: Implement `app/google_oauth.py`**

```python
"""Google OAuth2 (installed-app / loopback) — pure helpers + injectable HTTP."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import Any, Callable
from urllib.parse import urlencode

import httpx
from sqlmodel import Session

from app import settings_service as ss

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
USERINFO_URI = "https://www.googleapis.com/oauth2/v2/userinfo"
DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]

Poster = Callable[[str, dict[str, Any]], dict[str, Any]]


def _post(url: str, data: dict[str, Any]) -> dict[str, Any]:
    r = httpx.post(url, data=data, timeout=30)
    r.raise_for_status()
    return r.json()


def _get_json(url: str, access_token: str) -> dict[str, Any]:
    r = httpx.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=30)
    r.raise_for_status()
    return r.json()


def new_state() -> str:
    return secrets.token_urlsafe(24)


def build_auth_url(*, client_id: str, redirect_uri: str, state: str, scopes: list[str] = DEFAULT_SCOPES) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "include_granted_scopes": "true",
    }
    return f"{AUTH_URI}?{urlencode(params)}"


def _to_token(resp: dict[str, Any], now: datetime) -> dict[str, Any]:
    expires_in = int(resp.get("expires_in", 3600))
    return {
        "access_token": resp["access_token"],
        "refresh_token": resp.get("refresh_token"),
        "scope": resp.get("scope", ""),
        "expiry": (now + timedelta(seconds=expires_in)).isoformat(),
    }


def exchange_code(*, client_id, client_secret, code, redirect_uri, now, poster: Poster = _post) -> dict[str, Any]:
    resp = poster(
        TOKEN_URI,
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    return _to_token(resp, now)


def refresh(*, client_id, client_secret, refresh_token, now, poster: Poster = _post) -> dict[str, Any]:
    resp = poster(
        TOKEN_URI,
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    tok = _to_token(resp, now)
    if not tok.get("refresh_token"):
        tok["refresh_token"] = refresh_token  # refresh responses omit it
    return tok


def load_token(session: Session) -> dict[str, Any] | None:
    raw = ss.get_setting(session, ss.GOOGLE_OAUTH_TOKEN)
    return json.loads(raw) if raw else None


def save_token(session: Session, token: dict[str, Any], *, email: str | None = None) -> None:
    out = dict(token)
    existing = load_token(session)
    if email:
        out["email"] = email
    if existing:
        out.setdefault("refresh_token", existing.get("refresh_token"))
        out.setdefault("email", existing.get("email"))
    ss.set_setting(session, ss.GOOGLE_OAUTH_TOKEN, json.dumps(out))


def get_access_token(session: Session, *, now: datetime, poster: Poster = _post) -> str:
    tok = load_token(session)
    if not tok or not tok.get("refresh_token"):
        raise RuntimeError("Google account not connected")
    expiry = datetime.fromisoformat(tok["expiry"])
    if now < expiry - timedelta(seconds=60):
        return tok["access_token"]
    cid, secret = ss.resolve_google_client(session)
    if not cid or not secret:
        raise RuntimeError("Google client credentials missing")
    fresh = refresh(client_id=cid, client_secret=secret, refresh_token=tok["refresh_token"], now=now, poster=poster)
    save_token(session, fresh)
    return fresh["access_token"]


def fetch_email(access_token: str, *, getter: Callable[[str, str], dict[str, Any]] = _get_json) -> str | None:
    try:
        return getter(USERINFO_URI, access_token).get("email")
    except Exception:  # noqa: BLE001 — email is best-effort metadata
        return None


def status(session: Session) -> dict[str, Any]:
    tok = load_token(session)
    cid, _ = ss.resolve_google_client(session)
    return {
        "credentials_configured": bool(cid),
        "connected": bool(tok and tok.get("refresh_token")),
        "email": tok.get("email") if tok else None,
        "scopes": (tok.get("scope") if tok else "") or "",
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_google_oauth.py -q`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add app/settings_service.py app/google_oauth.py tests/test_google_oauth.py
git commit -m "feat(google): OAuth2 foundation (auth URL, code exchange, token refresh, status)"
```

---

### Task 2: Gmail connector (`gmail_service.py` + `external_id`)

**Files:**
- Modify: `app/models.py` (`Communication.external_id`)
- Modify: `app/db.py` (`_ensure_column`)
- Create: `app/gmail_service.py`
- Test: `tests/test_gmail_service.py`

- [ ] **Step 1: Add the column + migration**

In `app/models.py`, in `class Communication`, after `thread_key: ...`, add:
```python
    external_id: str | None = Field(default=None, index=True)  # provider message id (dedup)
```
In `app/db.py` `init_db`, after the existing `_ensure_column(...)` lines:
```python
    _ensure_column(engine, "communications", "external_id", "VARCHAR")
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_gmail_service.py`:
```python
from sqlmodel import Session, select

from app.db import engine
from app import gmail_service
from app.models import Communication


def _msg(mid, frm, subject="Hi", body_text="hello", internal="1718971200000"):
    import base64
    data = base64.urlsafe_b64encode(body_text.encode()).decode().rstrip("=")
    return {
        "id": mid,
        "threadId": "T-" + mid,
        "internalDate": internal,
        "snippet": "snippet",
        "payload": {
            "mimeType": "text/plain",
            "headers": [{"name": "From", "value": frm}, {"name": "Subject", "value": subject}],
            "body": {"data": data},
        },
    }


def _fetcher(messages):
    by_id = {m["id"]: m for m in messages}

    def fetch(url, access_token, params=None):
        if url.endswith("/messages"):
            return {"messages": [{"id": m["id"]} for m in messages]}
        mid = url.rsplit("/", 1)[-1]
        return by_id[mid]

    return fetch


def test_sync_creates_communications_and_dedupes():
    msgs = [
        _msg("m1", "Sarah <sarah@kore1.com>", "Interview?"),
        _msg("m2", "me@myself.com", "My reply"),  # outbound (from self)
    ]
    with Session(engine) as s:
        r1 = gmail_service.sync(s, access_token="AT", account_email="me@myself.com", fetcher=_fetcher(msgs))
        assert r1 == {"fetched": 2, "created": 2, "skipped": 0}
        rows = s.exec(select(Communication).where(Communication.channel == "email")).all()
        assert {c.external_id for c in rows} == {"m1", "m2"}
        inbound = next(c for c in rows if c.external_id == "m1")
        outbound = next(c for c in rows if c.external_id == "m2")
        assert inbound.direction.value == "inbound" and "hello" in inbound.body
        assert outbound.direction.value == "outbound"
        # re-running dedupes on external_id
        r2 = gmail_service.sync(s, access_token="AT", account_email="me@myself.com", fetcher=_fetcher(msgs))
        assert r2["created"] == 0 and r2["skipped"] == 2
```

- [ ] **Step 3: Run it to verify it fails**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_gmail_service.py -q`
Expected: FAIL (`ModuleNotFoundError: app.gmail_service`).

- [ ] **Step 4: Implement `app/gmail_service.py`**

```python
"""Gmail ingest → Communication rows (injectable HTTP for tests)."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
from sqlmodel import Session, select

from app import services
from app.models import Communication, CommChannel, CommDirection

LIST_URI = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
MSG_URI = "https://gmail.googleapis.com/gmail/v1/users/me/messages/{id}"

Fetcher = Callable[[str, str, dict[str, Any] | None], dict[str, Any]]


def _get(url: str, access_token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    r = httpx.get(url, headers={"Authorization": f"Bearer {access_token}"}, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _header(payload: dict, name: str) -> str:
    for h in payload.get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _addr(value: str) -> str:
    if "<" in value and ">" in value:
        return value[value.index("<") + 1 : value.index(">")].strip().lower()
    return value.strip().lower()


def _body_text(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data")
        if data:
            return base64.urlsafe_b64decode(data + "===").decode("utf-8", "replace")
    for part in payload.get("parts", []) or []:
        t = _body_text(part)
        if t:
            return t
    return ""


def map_message(msg: dict, *, account_email: str) -> dict[str, Any]:
    payload = msg.get("payload", {})
    inbound = _addr(_header(payload, "From")) != (account_email or "").lower()
    internal = int(msg.get("internalDate", "0")) / 1000
    occurred = (
        datetime.fromtimestamp(internal, tz=timezone.utc).replace(tzinfo=None) if internal else None
    )
    return {
        "external_id": msg["id"],
        "thread_key": msg.get("threadId"),
        "direction": CommDirection.inbound if inbound else CommDirection.outbound,
        "subject": _header(payload, "Subject") or "(no subject)",
        "body": _body_text(payload) or msg.get("snippet", ""),
        "occurred_at": occurred,
    }


def sync(
    session: Session,
    *,
    access_token: str,
    account_email: str,
    query: str = "newer_than:30d",
    max_messages: int = 50,
    fetcher: Fetcher = _get,
) -> dict[str, Any]:
    listing = fetcher(LIST_URI, access_token, {"q": query, "maxResults": max_messages})
    ids = [m["id"] for m in listing.get("messages", [])]
    created = skipped = 0
    for mid in ids:
        if session.exec(
            select(Communication).where(Communication.external_id == mid)
        ).first():
            skipped += 1
            continue
        f = map_message(fetcher(MSG_URI.format(id=mid), access_token, {"format": "full"}), account_email=account_email)
        c = services.record_communication(
            session,
            direction=f["direction"],
            channel=CommChannel.email,
            subject=f["subject"],
            body=f["body"],
            occurred_at=f["occurred_at"],
            thread_key=f["thread_key"],
        )
        c.external_id = f["external_id"]
        session.add(c)
        session.commit()
        created += 1
    return {"fetched": len(ids), "created": created, "skipped": skipped}
```

- [ ] **Step 5: Run the test + full gate**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_gmail_service.py -q` → PASS
Then `bash scripts/ci/gate.sh` → GATE PASSED.

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/db.py app/gmail_service.py tests/test_gmail_service.py
git commit -m "feat(google): Gmail sync -> Communications (dedup on external_id)"
```

---

### Task 3: Endpoints, Settings UI, and setup guide

**Files:**
- Modify: `app/config.py` (`google_redirect_uri`)
- Create: `app/routers/google.py`
- Modify: `app/main.py` (mount), `app/routers/settings.py` (save google creds + expose status)
- Modify: `frontend/app/components/SettingsBadge.tsx` (creds fields + Connect/Sync), `frontend/lib/api.ts` (fetchers)
- Create: `docs/google-setup.md`
- Test: `tests/test_google_api.py`

- [ ] **Step 1: Config + router**

In `app/config.py`, after the Google keep-alive/search knobs, add:
```python
    google_redirect_uri: str = "http://127.0.0.1:8000/api/google/oauth/callback"
```

Create `app/routers/google.py`:
```python
"""Google integration endpoints — status, OAuth connect, Gmail sync."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app import gmail_service, google_oauth as go, settings_service as ss
from app.config import get_config
from app.db import get_session
from app.models import _utcnow

router = APIRouter(prefix="/api/google", tags=["google"])


@router.get("/status")
def google_status(session: Session = Depends(get_session)) -> dict:
    return go.status(session)


@router.get("/oauth/start")
def oauth_start(session: Session = Depends(get_session)):
    cid, _ = ss.resolve_google_client(session)
    if not cid:
        raise HTTPException(status_code=400, detail="Set Google client id/secret in Settings first")
    state = go.new_state()
    ss.set_setting(session, ss.GOOGLE_OAUTH_STATE, state)
    url = go.build_auth_url(
        client_id=cid, redirect_uri=get_config().google_redirect_uri, state=state
    )
    return RedirectResponse(url)


@router.get("/oauth/callback")
def oauth_callback(
    code: str = Query(...), state: str = Query(...), session: Session = Depends(get_session)
):
    saved = ss.get_setting(session, ss.GOOGLE_OAUTH_STATE)
    if not saved or state != saved:
        raise HTTPException(status_code=400, detail="invalid oauth state")
    cid, secret = ss.resolve_google_client(session)
    tok = go.exchange_code(
        client_id=cid, client_secret=secret, code=code,
        redirect_uri=get_config().google_redirect_uri, now=_utcnow(),
    )
    go.save_token(session, tok, email=go.fetch_email(tok["access_token"]))
    return HTMLResponse(
        "<h3>Google connected ✓</h3><p>You can close this tab and return to Opportunity Hunter.</p>"
    )


@router.post("/gmail/sync")
def gmail_sync(query: str = "newer_than:30d", session: Session = Depends(get_session)) -> dict:
    token = go.get_access_token(session, now=_utcnow())
    email = (go.status(session).get("email")) or ""
    return gmail_service.sync(session, access_token=token, account_email=email, query=query)
```

In `app/main.py`: add `google` to the routers import and `app.include_router(google.router)`.

- [ ] **Step 2: Settings router — save creds + expose google status**

In `app/routers/settings.py`: add `google_client_id: str | None = None` and `google_client_secret: str | None = None` to `SettingsUpdate`; in `update_settings`, persist them via `ss.set_setting(session, ss.GOOGLE_CLIENT_ID, ...)` / `GOOGLE_CLIENT_SECRET` when not None. Add `google` to `SettingsView` as `google: dict` and in `_view` set `google=go.status(session)` (import `from app import google_oauth as go`). Never echo the secret.

- [ ] **Step 3: Failing API test**

Create `tests/test_google_api.py`:
```python
def test_google_status_default_disconnected(client):
    st = client.get("/api/google/status").json()
    assert st["connected"] is False and st["credentials_configured"] is False


def test_oauth_start_requires_credentials(client):
    # no creds yet → 400
    assert client.get("/api/google/oauth/start", follow_redirects=False).status_code == 400
    # set creds → redirects to Google
    client.put("/api/settings", json={"google_client_id": "cid", "google_client_secret": "sec"})
    r = client.get("/api/google/oauth/start", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "accounts.google.com" in r.headers["location"]


def test_oauth_callback_rejects_bad_state(client):
    client.put("/api/settings", json={"google_client_id": "cid", "google_client_secret": "sec"})
    assert client.get(
        "/api/google/oauth/callback?code=C&state=wrong", follow_redirects=False
    ).status_code == 400


def test_gmail_sync_runs_with_stubbed_oauth(client, monkeypatch):
    import app.routers.google as mod

    monkeypatch.setattr(mod.go, "get_access_token", lambda session, now: "AT")
    monkeypatch.setattr(mod.go, "status", lambda session: {"email": "me@x.com"})
    monkeypatch.setattr(
        mod.gmail_service, "sync",
        lambda session, **kw: {"fetched": 1, "created": 1, "skipped": 0},
    )
    r = client.post("/api/google/gmail/sync")
    assert r.status_code == 200 and r.json()["created"] == 1
```

- [ ] **Step 4: Run backend tests + gate**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_google_api.py -q` → PASS
Then `bash scripts/ci/gate.sh` → GATE PASSED.

- [ ] **Step 5: Minimal Settings UI**

Read `frontend/app/components/SettingsBadge.tsx` and follow its existing field pattern. Add:
- Two inputs (Google client ID, client secret) saved via the existing settings PUT (extend the `api.ts` settings type/updater to include `google_client_id`/`google_client_secret`, and read `google` status from GET `/api/settings`).
- A **Connect Google** link → `href="/api/google/oauth/start"` (opens in a new tab), shown when creds are configured; show the connected email when `google.connected`.
- A **Sync Gmail** button → `POST /api/google/gmail/sync` (add `syncGmail()` to `api.ts`), shows the returned counts.
Keep it compact; match the component's styling/tokens.
Run: `npm --prefix frontend install` then `npm --prefix frontend run build` → succeeds.

- [ ] **Step 6: Setup guide**

Create `docs/google-setup.md` with the steps: create a Google Cloud project; enable the Gmail API; configure the OAuth consent screen (External, add yourself as a Test user); create an **OAuth client ID → Desktop app**; copy client id/secret into Settings; ensure the authorized redirect/loopback is `http://127.0.0.1:8000/api/google/oauth/callback` (note Desktop clients allow loopback automatically); click **Connect Google** *from the machine running the server* (loopback constraint); then **Sync Gmail**. Note ingested mail appears under Attention → Untriaged messages and can be triaged with `email-analyser`.

- [ ] **Step 7: Commit**

```bash
git add app/config.py app/routers/google.py app/main.py app/routers/settings.py frontend/app/components/SettingsBadge.tsx frontend/lib/api.ts docs/google-setup.md tests/test_google_api.py
git commit -m "feat(google): connect/sync endpoints + Settings UI + setup guide"
```
