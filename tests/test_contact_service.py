from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import Contact, Opportunity, OpportunityType


def _opp(s: Session) -> Opportunity:
    o = Opportunity(type=OpportunityType.job, title="Role")
    s.add(o)
    s.commit()
    s.refresh(o)
    return o


def test_add_contact_creates_and_touches_opp():
    with Session(engine) as s:
        o = _opp(s)
        before = o.last_activity_at
        c = services.add_contact(s, name="Jane Recruiter", opportunity_id=o.id,
                                 role="Recruiter", link="https://linkedin.com/in/jane")
        assert c.id is not None and c.name == "Jane Recruiter" and c.role == "Recruiter"
        s.refresh(o)
        assert o.last_activity_at >= before


def test_add_contact_update_by_id():
    with Session(engine) as s:
        o = _opp(s)
        first = services.add_contact(s, name="Sam", opportunity_id=o.id)
        updated = services.add_contact(s, name="Sam Hire", opportunity_id=o.id,
                                       role="Hiring Manager", contact_id=first.id)
        assert updated.id == first.id and updated.role == "Hiring Manager"


def test_list_contacts_filters_by_opportunity():
    with Session(engine) as s:
        o1, o2 = _opp(s), _opp(s)
        services.add_contact(s, name="A", opportunity_id=o1.id)
        services.add_contact(s, name="B", opportunity_id=o2.id)
        assert len(services.list_contacts(s, opportunity_id=o1.id)) == 1
        assert len(services.list_contacts(s)) == 2
