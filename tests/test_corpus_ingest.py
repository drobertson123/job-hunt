# tests/test_corpus_ingest.py
from __future__ import annotations

import hashlib

from sqlmodel import Session, select

from app.corpus_service import ingest_document
from app.db import engine
from app.models import Chunk, Document, DocumentMediaType, DocumentSource


def _fake_embedder(dim=8):
    def embed(texts):
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            out.append([b / 255.0 for b in h[:dim]])
        return out
    return embed


def test_ingest_persists_document_and_chunks():
    big = "Resume.\n\n" + ("alpha beta gamma delta " * 300)
    with Session(engine) as s:
        doc = ingest_document(
            s, title="resume.md", source_kind=DocumentSource.paste,
            media_type=DocumentMediaType.md, data=big.encode(),
            embedder=_fake_embedder(),
        )
        doc_id = doc.id
        chunks = s.exec(select(Chunk).where(Chunk.document_id == doc_id)).all()
    assert doc_id is not None
    assert len(chunks) > 1
    assert all(c.embedding and c.embedding_model for c in chunks)
    assert doc.char_count == len(big.strip())


def test_ingest_is_idempotent_on_content_hash():
    text = "identical content for dedup".encode()
    with Session(engine) as s:
        d1 = ingest_document(s, title="a.txt", source_kind=DocumentSource.upload,
                             media_type=DocumentMediaType.txt, data=text, embedder=_fake_embedder())
        d2 = ingest_document(s, title="a-again.txt", source_kind=DocumentSource.upload,
                             media_type=DocumentMediaType.txt, data=text, embedder=_fake_embedder())
        h = hashlib.sha256("identical content for dedup".encode()).hexdigest()
        docs = s.exec(select(Document).where(Document.content_hash == h)).all()
        all_chunks = s.exec(select(Chunk)).all()
    assert len(docs) == 1  # replaced, not duplicated
    assert d2.id is not None
    # The single-chunk doc was replaced, so exactly one chunk total remains —
    # the old document's chunk was deleted, not left orphaned. (A document_id
    # filter would be unreliable here: SQLite reuses the deleted row's PK.)
    assert len(all_chunks) == 1
