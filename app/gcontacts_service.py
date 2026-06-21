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
