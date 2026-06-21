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
