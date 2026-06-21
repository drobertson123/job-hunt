from sqlmodel import Session

from app.db import engine
from app import capabilities as caps, services
from app.models import Opportunity, OpportunityType


def _cap(name):
    return next(c for c in caps.CAPABILITIES if c.name == name)


def test_network_scan_prompt_inlines_contacts():
    with Session(engine) as s:
        services.add_contact(s, name="Jane Smith", organization="Stripe")
        contacts = services.list_contacts(s)
    prompt = caps.build_prompt(_cap("network-scan"), contacts=contacts)
    assert "Contacts (grouped by organization):" in prompt
    assert "Stripe" in prompt and "Jane Smith" in prompt


def test_apply_prep_prompt_has_opportunity_not_contacts():
    opp = Opportunity(type=OpportunityType.job, title="Role", organization="Co")
    prompt = caps.build_prompt(_cap("apply-prep"), opportunity=opp)
    assert "Opportunity:" in prompt
    assert "Contacts (grouped by organization):" not in prompt
