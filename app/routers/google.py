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
