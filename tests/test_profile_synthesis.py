# tests/test_profile_synthesis.py
from __future__ import annotations

from collections.abc import AsyncIterator

from claude_agent_sdk import AssistantMessage, TextBlock
from sqlmodel import Session, select

from app.corpus_service import ingest_document
from app.db import engine
from app.models import Document, DocumentMediaType, DocumentSource, Profile
from app.profile_service import ProfileSchema, synthesize_profile


def _fake_embedder(texts):
    return [[1.0, 0.0] for _ in texts]


def _fake_query(reply_text: str, calls: list[dict]):
    async def fake(*, prompt, options) -> AsyncIterator:
        calls.append({"prompt": prompt, "options": options})
        yield AssistantMessage(content=[TextBlock(text=reply_text)], model="fake-model")
    return fake


async def test_synthesize_writes_profile_row_and_grounds_prompt():
    with Session(engine) as s:
        ingest_document(s, title="cv.md", source_kind=DocumentSource.paste,
                        media_type=DocumentMediaType.md,
                        data=b"Jane Doe. Staff ML Engineer. PyTorch, MLOps.",
                        embedder=_fake_embedder)
    reply = (
        '{"headline": "Staff ML Engineer", "summary": "ML platform leader.", '
        '"skills": ["PyTorch", "MLOps"], "experience": [], "achievements": [], '
        '"target_titles": ["Staff ML Engineer"], "locations": []}'
    )
    calls: list[dict] = []
    with Session(engine) as s:
        profile = await synthesize_profile(s, query_fn=_fake_query(reply, calls))
        profile_id = profile.id

    with Session(engine) as s:
        row = s.get(Profile, profile_id)
    assert row is not None
    assert row.headline == "Staff ML Engineer"
    assert "PyTorch" in row.skills
    assert row.source_doc_count == 1
    # corpus text is in the prompt (grounding) + anti-fabrication instruction present
    assert "Jane Doe" in calls[0]["prompt"]
    assert "never invent" in calls[0]["prompt"].lower()


async def test_synthesize_overwrites_single_row():
    reply = '{"headline": "Second", "summary": null, "skills": [], "experience": [], "achievements": [], "target_titles": [], "locations": []}'
    calls: list[dict] = []
    with Session(engine) as s:
        ingest_document(s, title="cv.md", source_kind=DocumentSource.paste,
                        media_type=DocumentMediaType.md,
                        data=b"Some person. Engineer.",
                        embedder=_fake_embedder)
        await synthesize_profile(s, query_fn=_fake_query(reply, calls))
        await synthesize_profile(s, query_fn=_fake_query(reply, calls))
    with Session(engine) as s:
        rows = s.exec(select(Profile)).all()
    assert len(rows) == 1 and rows[0].headline == "Second"


async def test_synthesize_empty_corpus_raises():
    import pytest

    # The autouse _clear_corpus fixture (Task 2, Step 0) guarantees an empty corpus.
    calls: list[dict] = []
    with pytest.raises(ValueError, match="empty"):
        with Session(engine) as s:
            await synthesize_profile(s, query_fn=_fake_query("{}", calls))
