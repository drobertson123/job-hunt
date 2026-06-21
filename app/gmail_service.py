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
