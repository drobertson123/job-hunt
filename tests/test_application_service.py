from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import ApplicationStatus, Opportunity, OpportunityType


def _make_opp(s: Session) -> Opportunity:
    opp = Opportunity(type=OpportunityType.job, title="Staff ML Engineer")
    s.add(opp)
    s.commit()
    s.refresh(opp)
    return opp


def test_record_application_creates_with_defaults_and_touches_opp():
    with Session(engine) as s:
        opp = _make_opp(s)
        before = opp.last_activity_at
        app_row = services.record_application(
            s, opportunity_id=opp.id, portal_url="https://boards.greenhouse.io/x"
        )
        assert app_row.id is not None
        assert app_row.opportunity_id == opp.id
        assert app_row.status == ApplicationStatus.draft
        s.refresh(opp)
        assert opp.last_activity_at >= before


def test_record_application_updates_existing_by_id():
    with Session(engine) as s:
        opp = _make_opp(s)
        a = services.record_application(s, opportunity_id=opp.id)
        updated = services.record_application(
            s, opportunity_id=opp.id, status=ApplicationStatus.submitted,
            portal_url="https://lever.co/y", application_id=a.id,
        )
        assert updated.id == a.id
        assert updated.status == ApplicationStatus.submitted
        assert updated.portal_url == "https://lever.co/y"
        assert len(services.list_applications(s, opportunity_id=opp.id)) == 1


def test_list_applications_filters_by_opportunity():
    with Session(engine) as s:
        o1, o2 = _make_opp(s), _make_opp(s)
        services.record_application(s, opportunity_id=o1.id)
        services.record_application(s, opportunity_id=o2.id)
        assert len(services.list_applications(s, opportunity_id=o1.id)) == 1
        assert len(services.list_applications(s)) == 2
