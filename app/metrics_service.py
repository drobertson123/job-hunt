"""Pipeline metrics aggregated from Applications + Opportunities (deterministic)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from app.models import Application, ApplicationStatus, Opportunity, _utcnow

_APPLIED = {ApplicationStatus.submitted, ApplicationStatus.under_review, ApplicationStatus.interviewing, ApplicationStatus.offer, ApplicationStatus.rejected}
_SCREEN = {ApplicationStatus.under_review, ApplicationStatus.interviewing, ApplicationStatus.offer}
_INTERVIEW = {ApplicationStatus.interviewing, ApplicationStatus.offer}
_OFFER = {ApplicationStatus.offer}
_ACTIVE_STAGES = {"active", "in_dialogue"}


def _rate(n: int, d: int) -> int:
    return round(100 * n / d) if d else 0


def compute_metrics(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or _utcnow()
    apps = list(session.exec(select(Application)).all())
    statuses = [a.status for a in apps]
    applied = sum(s in _APPLIED for s in statuses)
    screening = sum(s in _SCREEN for s in statuses)
    interview = sum(s in _INTERVIEW for s in statuses)
    offer = sum(s in _OFFER for s in statuses)

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_month = sum(a.created_at >= month_start for a in apps)

    funnel = [
        {"label": "Applied", "count": applied, "rate": None},
        {"label": "Screening", "count": screening, "rate": _rate(screening, applied)},
        {"label": "Interview", "count": interview, "rate": _rate(interview, screening)},
        {"label": "Offer", "count": offer, "rate": _rate(offer, interview)},
    ]

    week0 = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    volume = []
    for w in range(7, -1, -1):
        start = week0 - timedelta(weeks=w)
        end = start + timedelta(days=7)
        volume.append({"week": start.strftime("%b %d"), "count": sum(start <= a.created_at < end for a in apps)})

    opps = list(session.exec(select(Opportunity)).all())
    src = Counter((o.source or "unknown") for o in opps)
    sources = [{"source": k, "count": v} for k, v in src.most_common(6)]
    active = sum(o.stage in _ACTIVE_STAGES for o in opps)

    return {
        "kpis": {
            "total_applications": len(apps),
            "this_month": this_month,
            "response_rate": _rate(screening, applied),
            "interview_rate": _rate(interview, screening),
            "active": active,
        },
        "funnel": funnel,
        "volume": volume,
        "sources": sources,
    }
