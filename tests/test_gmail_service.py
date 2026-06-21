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
