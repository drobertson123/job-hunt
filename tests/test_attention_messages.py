from sqlmodel import Session

from app.db import engine
from app import services
from app.models import CommChannel, CommDirection, Opportunity, OpportunityType
from app.orchestration import needs_attention


def test_unlinked_inbound_message_surfaces_in_attention():
    with Session(engine) as s:
        services.record_communication(
            s, direction=CommDirection.inbound, channel=CommChannel.sms,
            subject="SMS from +1", body="call me",
        )  # unlinked → should surface
        att = needs_attention(s)
    msgs = [i for i in att["items"] if i["kind"] == "untriaged_message"]
    assert len(msgs) == 1
    assert att["counts"]["untriaged_messages"] == 1


def test_linked_inbound_message_does_not_surface():
    with Session(engine) as s:
        o = Opportunity(type=OpportunityType.job, title="Linked")
        s.add(o); s.commit(); s.refresh(o)
        services.record_communication(
            s, direction=CommDirection.inbound, channel=CommChannel.sms,
            opportunity_id=o.id, subject="SMS", body="hi",
        )
        att = needs_attention(s)
    assert all(i["kind"] != "untriaged_message" for i in att["items"])
