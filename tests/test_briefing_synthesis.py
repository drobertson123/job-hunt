from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from claude_agent_sdk import AssistantMessage, TextBlock
from sqlmodel import Session

from app.briefing_service import BriefingSchema, get_briefing, synthesize_briefing
from app.corpus_service import ingest_document
from app.db import engine
from app.models import (
    Company,
    DocumentMediaType,
    DocumentSource,
    Opportunity,
    OpportunityType,
)

_REPLY = (
    '{"summary": "Strong platform-eng fit.", "facts": ['
    '{"key": "salary_range", "question": "Salary range?", "answer": "unknown",'
    ' "confidence": 0.1, "source": null},'
    '{"key": "why_fit", "question": "Why a fit?", "answer": "MLOps depth.",'
    ' "confidence": 0.8, "source": "cv.md"}]}'
)


def _fake_query(reply_text: str, calls: list[dict]):
    async def fake(*, prompt, options) -> AsyncIterator:
        calls.append({"prompt": prompt, "options": options})
        yield AssistantMessage(content=[TextBlock(text=reply_text)], model="fake")
    return fake


def _fake_embedder(texts):
    return [[1.0, 0.0] for _ in texts]


async def test_synthesize_writes_row_and_grounds_prompt():
    with Session(engine) as s:
        co = Company(name="Globex", industry="Energy")
        s.add(co)
        s.commit()
        s.refresh(co)
        opp = Opportunity(type=OpportunityType.job, title="Staff ML Engineer",
                          organization="Globex", company_id=co.id,
                          summary="Own the ML platform.")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        ingest_document(s, title="cv.md", source_kind=DocumentSource.paste,
                        media_type=DocumentMediaType.md,
                        data=b"Jane Doe. MLOps, PyTorch.", embedder=_fake_embedder)
        opp_id = opp.id

    calls: list[dict] = []
    with Session(engine) as s:
        b = await synthesize_briefing(s, opportunity_id=opp_id,
                                      query_fn=_fake_query(_REPLY, calls))
        bid = b.id

    with Session(engine) as s:
        from app.models import Briefing
        row = s.get(Briefing, bid)
    assert row is not None
    assert row.opportunity_id == opp_id and row.company_id is not None
    assert row.summary == "Strong platform-eng fit."
    assert len(row.facts) == 2
    assert row.facts[0]["key"] == "salary_range"  # enum serialized to its value
    assert row.source_hash
    # grounding: opportunity title, company name, corpus, anti-fabrication instruction
    p = calls[0]["prompt"]
    assert "Staff ML Engineer" in p and "Globex" in p and "Jane Doe" in p
    assert "never invent" in p.lower()


async def test_synthesize_upserts_single_row_per_opportunity():
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        opp_id = opp.id
    calls: list[dict] = []
    with Session(engine) as s:
        first = await synthesize_briefing(s, opportunity_id=opp_id,
                                          query_fn=_fake_query(_REPLY, calls))
        first_id = first.id
        second = await synthesize_briefing(s, opportunity_id=opp_id,
                                           query_fn=_fake_query(_REPLY, calls))
        assert second.id == first_id
        assert get_briefing(s, opp_id) is not None


async def test_synthesize_missing_opportunity_raises():
    with Session(engine) as s:
        with pytest.raises(ValueError):
            await synthesize_briefing(s, opportunity_id="nope",
                                      query_fn=_fake_query(_REPLY, []))
