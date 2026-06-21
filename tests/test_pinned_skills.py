from __future__ import annotations

from collections.abc import AsyncIterator

from claude_agent_sdk import AssistantMessage, TextBlock
from sqlmodel import Session, select

from app.db import engine
from app.models import Profile
from app.profile_service import set_pinned_skills, synthesize_profile


def test_set_pinned_skills_creates_then_updates_and_dedupes():
    with Session(engine) as s:
        p = set_pinned_skills(s, ["  Python ", "Python", "MLOps", ""])
        assert p.pinned_skills == ["Python", "MLOps"]  # trimmed, deduped, empties dropped
        p2 = set_pinned_skills(s, ["Leadership"])
        assert p2.id == p.id and p2.pinned_skills == ["Leadership"]


async def test_synthesize_preserves_pinned_skills():
    with Session(engine) as s:
        set_pinned_skills(s, ["Sparkplug B"])
    reply = ('{"headline":"X","summary":null,"skills":["PyTorch"],"experience":[],'
             '"achievements":[],"target_titles":[],"locations":[]}')

    async def fake(*, prompt, options) -> AsyncIterator:
        yield AssistantMessage(content=[TextBlock(text=reply)], model="fake")

    # seed a corpus doc so synthesize doesn't ValueError on empty corpus
    from app.corpus_service import ingest_document
    from app.models import DocumentMediaType, DocumentSource
    with Session(engine) as s:
        ingest_document(s, title="cv.md", source_kind=DocumentSource.paste,
                        media_type=DocumentMediaType.md, data=b"Jane. PyTorch.",
                        embedder=lambda texts: [[1.0, 0.0] for _ in texts])
        await synthesize_profile(s, query_fn=fake)
    with Session(engine) as s:
        row = s.exec(select(Profile)).first()
    assert row.skills == ["PyTorch"] and row.pinned_skills == ["Sparkplug B"]


def test_patch_profile_endpoint(client):
    res = client.patch("/api/corpus/profile", json={"pinned_skills": ["DTDL", "UNS"]})
    assert res.status_code == 200 and res.json()["pinned_skills"] == ["DTDL", "UNS"]
    got = client.get("/api/corpus/profile").json()
    assert got["pinned_skills"] == ["DTDL", "UNS"]
