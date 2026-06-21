"""Minimal RFC 5545 iCalendar writer for interview events (stdlib only).

ponytail: stored datetimes are naive wall-clock; DTSTART/DTEND are emitted as
*floating* local time (no Z) so a user-entered time shows at that clock time in
any viewer. DTSTAMP is UTC (Z), as the spec requires.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.models import InterviewEvent


def _esc(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _floating(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


def _stamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%SZ")


def _vevent(ev: InterviewEvent, *, now: datetime) -> list[str]:
    end = ev.ends_at or (ev.starts_at + timedelta(hours=1))
    lines = [
        "BEGIN:VEVENT",
        f"UID:interview-{ev.id}@opportunity-hunter",
        f"DTSTAMP:{_stamp(now)}",
        f"DTSTART:{_floating(ev.starts_at)}",
        f"DTEND:{_floating(end)}",
        f"SUMMARY:{_esc(ev.title)}",
    ]
    if ev.location:
        lines.append(f"LOCATION:{_esc(ev.location)}")
    if ev.notes:
        lines.append(f"DESCRIPTION:{_esc(ev.notes)}")
    lines.append("END:VEVENT")
    return lines


def to_ics(events: list[InterviewEvent], *, now: datetime) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Opportunity Hunter//Interviews//EN",
        "CALSCALE:GREGORIAN",
    ]
    for ev in events:
        lines.extend(_vevent(ev, now=now))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
