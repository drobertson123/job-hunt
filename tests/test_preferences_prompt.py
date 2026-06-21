from sqlmodel import Session

from app.db import engine
from app import capabilities as caps, profile_service as ps
from app.models import Opportunity, OpportunityType


def _cap(name):
    return next(c for c in caps.CAPABILITIES if c.name == name)


def test_fit_analysis_prompt_includes_preferences():
    with Session(engine) as s:
        profile = ps.set_preferences(s, dealbreakers=["on-site only"], must_haves=["staff+"])
    opp = Opportunity(type=OpportunityType.job, title="Role", organization="Co")
    prompt = caps.build_prompt(_cap("fit-analysis"), opportunity=opp, profile=profile)
    assert "Job preferences:" in prompt
    assert "on-site only" in prompt and "staff+" in prompt


def test_cover_letter_prompt_omits_preferences():
    opp = Opportunity(type=OpportunityType.job, title="Role", organization="Co")
    prompt = caps.build_prompt(_cap("cover-letter"), opportunity=opp, profile=None)
    assert "Job preferences:" not in prompt
