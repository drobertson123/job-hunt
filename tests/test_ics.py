from datetime import datetime

from app.ics import to_ics
from app.models import InterviewEvent


def _ev(**kw):
    base = dict(id=1, title="Phone screen", starts_at=datetime(2026, 7, 1, 14, 0))
    base.update(kw)
    return InterviewEvent(**base)


def test_to_ics_basic_structure():
    now = datetime(2026, 6, 21, 12, 0)
    out = to_ics([_ev()], now=now)
    assert out.startswith("BEGIN:VCALENDAR")
    assert "END:VCALENDAR" in out
    assert "BEGIN:VEVENT" in out
    assert "UID:interview-1@opportunity-hunter" in out
    assert "DTSTART:20260701T140000" in out          # floating (no Z)
    assert "DTEND:20260701T150000" in out             # +1h default
    assert "DTSTAMP:20260621T120000Z" in out          # UTC stamp
    assert "\r\n" in out                              # CRLF


def test_to_ics_escapes_and_multiple_events():
    now = datetime(2026, 6, 21, 12, 0)
    out = to_ics(
        [_ev(id=1, title="Onsite, round 2; final"), _ev(id=2, title="Call")],
        now=now,
    )
    assert out.count("BEGIN:VEVENT") == 2
    assert "SUMMARY:Onsite\\, round 2\\; final" in out


def test_to_ics_normalizes_crlf_in_notes():
    now = datetime(2026, 6, 21, 12, 0)
    out = to_ics([_ev(notes="line1\r\nline2\rline3")], now=now)
    assert "DESCRIPTION:line1\\nline2\\nline3" in out
    # no bare CR survives inside a content value
    assert "\rline" not in out
