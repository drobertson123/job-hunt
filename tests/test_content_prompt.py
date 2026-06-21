from sqlmodel import Session

from app.db import engine
from app import capabilities as caps, services
from app.models import ContentBlockKind, Opportunity, OpportunityType


def _cap(name):
    return next(c for c in caps.CAPABILITIES if c.name == name)


def test_cv_tailor_prompt_includes_content_library():
    with Session(engine) as s:
        services.add_content_block(s, kind=ContentBlockKind.headline, text="Digital Twin Leader", audience="technical")
        blocks = services.list_content_blocks(s)
    opp = Opportunity(type=OpportunityType.job, title="Role", organization="Co")
    prompt = caps.build_prompt(_cap("cv-tailor"), opportunity=opp, content_blocks=blocks)
    assert "Content library" in prompt and "Digital Twin Leader" in prompt


def test_cover_letter_prompt_omits_content_library():
    opp = Opportunity(type=OpportunityType.job, title="Role", organization="Co")
    prompt = caps.build_prompt(_cap("cover-letter"), opportunity=opp, content_blocks=[])
    assert "Content library" not in prompt
