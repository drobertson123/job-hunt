# tests/test_corpus_live.py
from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlmodel import Session

from app.corpus_service import default_embedder, ingest_document, search
from app.db import engine
from app.models import DocumentMediaType, DocumentSource, Profile
from app.profile_service import synthesize_profile

FIX = Path(__file__).parent / "fixtures" / "corpus" / "live_brief.md"


@pytest.mark.skipif(
    not os.environ.get("OH_RUN_LIVE_PROBE"),
    reason="set OH_RUN_LIVE_PROBE=1 to run the live corpus probe (needs OpenAI key + authed claude CLI)",
)
async def test_live_ingest_search_and_synthesize():
    with Session(engine) as s:
        embedder = default_embedder(s)  # raises clearly if no key
        ingest_document(s, title="live_brief.md", source_kind=DocumentSource.upload,
                        media_type=DocumentMediaType.md, data=FIX.read_bytes(),
                        embedder=embedder)
        hits = search(s, "PyTorch model serving experience", embedder=embedder, k=3)
        assert hits and "PyTorch" in hits[0].chunk_text

        profile = await synthesize_profile(s)
        pid = profile.id
    with Session(engine) as s:
        row = s.get(Profile, pid)
    assert row is not None
    assert row.skills, "profile should extract at least one corpus-grounded skill"
    assert any("engineer" in t.lower() for t in row.target_titles)
