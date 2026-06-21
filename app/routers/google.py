"""Google integration endpoints — status, OAuth connect, Gmail sync."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app import gcal_service, gcontacts_service, gmail_service, google_oauth as go, settings_service as ss
from app.config import get_config
from app.db import get_session
from app.models import _utcnow

router = APIRouter(prefix="/api/google", tags=["google"])


@router.get("/status")
def google_status(session: Session = Depends(get_session)) -> dict:
    return go.status(session)


@router.get("/oauth/start")
def oauth_start(session: Session = Depends(get_session)):
    cid, secret = ss.resolve_google_client(session)
    if not cid or not secret:
        raise HTTPException(status_code=400, detail="Set Google client id AND secret in Settings first")
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
    ss.set_setting(session, ss.GOOGLE_OAUTH_STATE, "")  # consume the state (no replay)
    return HTMLResponse(
        "<h3>Google connected ✓</h3><p>You can close this tab and return to Opportunity Hunter.</p>"
    )


def _access_token(session: Session) -> str:
    """Resolve a Google access token, surfacing a not-connected state as a clean 400."""
    try:
        return go.get_access_token(session, now=_utcnow())
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/calendar/sync")
def calendar_sync(session: Session = Depends(get_session)) -> dict:
    token = _access_token(session)
    return gcal_service.sync_upcoming(session, access_token=token)


@router.post("/contacts/import")
def contacts_import(session: Session = Depends(get_session)) -> dict:
    token = _access_token(session)
    return gcontacts_service.import_contacts(session, access_token=token)


@router.post("/contacts/{contact_id}/push")
def contact_push(contact_id: int, session: Session = Depends(get_session)) -> dict:
    from app.models import Contact

    contact = session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="contact not found")
    token = _access_token(session)
    rn = gcontacts_service.push_contact(session, contact, access_token=token)
    return {"resource_name": rn}


@router.post("/gmail/sync")
def gmail_sync(query: str = "newer_than:30d", session: Session = Depends(get_session)) -> dict:
    token = _access_token(session)
    email = (go.status(session).get("email")) or ""
    if not email:
        # Backfill the account email (needed to label inbound vs outbound correctly).
        email = go.fetch_email(token) or ""
        if email:
            go.save_token(session, go.load_token(session) or {}, email=email)
    if not email:
        raise HTTPException(
            status_code=400,
            detail="Could not determine the connected Google account email; reconnect Google.",
        )
    return gmail_service.sync(session, access_token=token, account_email=email, query=query)
