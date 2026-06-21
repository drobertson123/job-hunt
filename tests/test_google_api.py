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
