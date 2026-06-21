from datetime import datetime, timedelta

from sqlmodel import Session

from app.db import engine
from app import services, gcal_service as gc
from app.models import InterviewKind


def _fake_request(log):
    def req(method, url, access_token, *, json=None, params=None):
        log.append((method, url, json))
        if method == "POST":
            return {"id": "evt-123"}
        return {}
    return req


def test_event_body_shape():
    iv = type("I", (), {})()
    iv.title = "Onsite"; iv.location = "HQ"; iv.notes = "bring laptop"
    iv.starts_at = datetime(2026, 7, 1, 14, 0); iv.ends_at = None
    iv.gcal_event_id = None
    body = gc.event_body(iv)
    assert body["summary"] == "Onsite"
    assert body["start"] == {"dateTime": "2026-07-01T14:00:00", "timeZone": "UTC"}
    assert body["end"] == {"dateTime": "2026-07-01T15:00:00", "timeZone": "UTC"}  # +1h
    assert body["location"] == "HQ" and body["description"] == "bring laptop"


def test_push_interview_creates_then_updates():
    log = []
    with Session(engine) as s:
        iv = services.add_interview(s, title="Call", starts_at=datetime(2999, 1, 1, 9, 0), kind=InterviewKind.phone)
        eid = gc.push_interview(s, iv, access_token="AT", request=_fake_request(log))
        assert eid == "evt-123" and iv.gcal_event_id == "evt-123"
        assert log[0][0] == "POST"
        # second push → PATCH (already linked)
        log2 = []
        gc.push_interview(s, iv, access_token="AT", request=_fake_request(log2))
        assert log2[0][0] == "PATCH" and "evt-123" in log2[0][1]


def test_sync_upcoming_counts():
    log = []
    with Session(engine) as s:
        services.add_interview(s, title="A", starts_at=datetime(2999, 1, 1, 9, 0))
        services.add_interview(s, title="B", starts_at=datetime(2999, 2, 1, 9, 0))
        services.add_interview(s, title="Past", starts_at=datetime(2000, 1, 1, 9, 0))
        r = gc.sync_upcoming(s, access_token="AT", request=_fake_request(log), now=datetime(2026, 6, 21, 12, 0))
    assert r == {"pushed": 2, "updated": 0}


def test_delete_event_swallows_errors():
    def boom(*a, **k):
        raise RuntimeError("404")
    gc.delete_event("AT", "evt-x", request=boom)  # must not raise
