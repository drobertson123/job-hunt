# tests/test_corpus_models.py
from __future__ import annotations

from sqlmodel import Session

from app.db import engine
from app.models import Chunk, Document, DocumentMediaType, DocumentSource, Profile


def test_document_chunk_roundtrip():
    with Session(engine) as s:
        doc = Document(
            title="resume.md",
            source_kind=DocumentSource.paste,
            media_type=DocumentMediaType.md,
            raw_text="hello world",
            content_hash="abc123",
            char_count=11,
        )
        s.add(doc)
        s.commit()
        s.refresh(doc)
        chunk = Chunk(
            document_id=doc.id, seq=0, text="hello world",
            embedding=b"\x00\x00", embedding_model="text-embedding-3-small",
        )
        s.add(chunk)
        s.commit()
        s.refresh(chunk)
        assert doc.id is not None and chunk.id is not None
        assert chunk.document_id == doc.id


def test_profile_json_fields_default_empty():
    p = Profile()
    assert p.skills == [] and p.experience == [] and p.target_titles == []
