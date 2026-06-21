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


def test_gmail_sync_400_when_account_email_unknown(client, monkeypatch):
    import app.routers.google as mod

    monkeypatch.setattr(mod.go, "get_access_token", lambda session, now: "AT")
    monkeypatch.setattr(mod.go, "status", lambda session: {})            # no email
    monkeypatch.setattr(mod.go, "fetch_email", lambda token: None)       # backfill fails
    r = client.post("/api/google/gmail/sync")
    assert r.status_code == 400


def test_oauth_callback_clears_state(client, monkeypatch):
    import app.routers.google as mod
    from app import settings_service as ss
    from app.db import engine
    from sqlmodel import Session

    client.put("/api/settings", json={"google_client_id": "cid", "google_client_secret": "sec"})
    # plant a known state, then drive the callback with it
    with Session(engine) as s:
        ss.set_setting(s, ss.GOOGLE_OAUTH_STATE, "ST")
    monkeypatch.setattr(mod.go, "exchange_code", lambda **kw: {
        "access_token": "AT", "refresh_token": "RT", "scope": "s", "expiry": "2099-01-01T00:00:00"})
    monkeypatch.setattr(mod.go, "fetch_email", lambda token: "me@x.com")
    assert client.get("/api/google/oauth/callback?code=C&state=ST", follow_redirects=False).status_code == 200
    with Session(engine) as s:
        assert (ss.get_setting(s, ss.GOOGLE_OAUTH_STATE) or "") == ""  # consumed


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
