from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import (
    CommChannel,
    CommDirection,
    Communication,
    Opportunity,
    OpportunityType,
    _utcnow,
)


def _opp(s: Session) -> Opportunity:
    o = Opportunity(type=OpportunityType.job, title="Role")
    s.add(o)
    s.commit()
    s.refresh(o)
    return o


def test_record_communication_creates_and_touches_opp():
    with Session(engine) as s:
        o = _opp(s)
        before = o.last_activity_at
        c = services.record_communication(
            s, direction=CommDirection.inbound, channel=CommChannel.email,
            opportunity_id=o.id, subject="Re: interview",
        )
        assert c.id is not None
        assert c.direction == CommDirection.inbound and c.channel == CommChannel.email
        assert c.occurred_at is not None  # model default applied
        s.refresh(o)
        assert o.last_activity_at >= before


def test_record_communication_updates_by_id_without_clobbering_occurred_at():
    with Session(engine) as s:
        o = _opp(s)
        first = services.record_communication(
            s, direction=CommDirection.outbound, channel=CommChannel.sms,
            opportunity_id=o.id, follow_up_due_at=_utcnow() + timedelta(days=1),
        )
        original_occurred = first.occurred_at
        updated = services.record_communication(
            s, direction=CommDirection.outbound, channel=CommChannel.phone,
            opportunity_id=o.id, communication_id=first.id,  # occurred_at omitted
        )
        assert updated.id == first.id
        assert updated.channel == CommChannel.phone
        assert updated.occurred_at == original_occurred  # not clobbered to None
        assert updated.follow_up_due_at is None  # cleared (arg omitted)


def test_list_communications_filters_by_opportunity():
    with Session(engine) as s:
        o1, o2 = _opp(s), _opp(s)
        services.record_communication(s, direction=CommDirection.inbound,
                                      channel=CommChannel.email, opportunity_id=o1.id)
        services.record_communication(s, direction=CommDirection.inbound,
                                      channel=CommChannel.email, opportunity_id=o2.id)
        assert len(services.list_communications(s, opportunity_id=o1.id)) == 1
        assert len(services.list_communications(s)) == 2
