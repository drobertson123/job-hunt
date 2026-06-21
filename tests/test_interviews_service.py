from datetime import datetime

from sqlmodel import Session

from app.db import engine
from app import services
from app.models import InterviewEvent, InterviewKind


def test_add_list_delete_interview_roundtrip():
    with Session(engine) as s:
        ev = services.add_interview(
            s, title="Phone screen", starts_at=datetime(2026, 7, 1, 14, 0),
            kind=InterviewKind.phone, location="Zoom", notes="bring questions",
        )
        assert ev.id is not None
        got = services.list_interviews(s)
        assert any(x.id == ev.id for x in got)
        assert services.delete_interview(s, ev.id) is True
        assert services.delete_interview(s, ev.id) is False
        assert all(x.id != ev.id for x in services.list_interviews(s))


def test_list_interviews_upcoming_and_order():
    with Session(engine) as s:
        past = services.add_interview(s, title="Past", starts_at=datetime(2000, 1, 1, 9, 0))
        soon = services.add_interview(s, title="Soon", starts_at=datetime(2999, 1, 1, 9, 0))
        later = services.add_interview(s, title="Later", starts_at=datetime(2999, 2, 1, 9, 0))
        upcoming = services.list_interviews(s, upcoming=True)
        ids = [x.id for x in upcoming]
        assert soon.id in ids and later.id in ids and past.id not in ids
        # ordered ascending by starts_at
        assert ids.index(soon.id) < ids.index(later.id)
