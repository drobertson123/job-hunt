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
