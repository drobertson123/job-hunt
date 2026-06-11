# tests/test_corpus_search.py
from __future__ import annotations

from sqlmodel import Session

from app.corpus_service import ChunkHit, ingest_document, search
from app.db import engine
from app.models import DocumentMediaType, DocumentSource

VOCAB = ["python", "marketing", "kubernetes", "sales", "pytorch"]


def _lexical_embedder(texts):
    # term-frequency over a fixed vocab → meaningful cosine ranking
    return [[float(t.lower().count(w)) for w in VOCAB] for t in texts]


def test_search_ranks_relevant_chunk_first():
    with Session(engine) as s:
        ingest_document(s, title="eng.md", source_kind=DocumentSource.paste,
                        media_type=DocumentMediaType.md,
                        data=b"python python pytorch kubernetes backend engineer",
                        embedder=_lexical_embedder)
        ingest_document(s, title="mkt.md", source_kind=DocumentSource.paste,
                        media_type=DocumentMediaType.md,
                        data=b"marketing marketing sales brand campaigns",
                        embedder=_lexical_embedder)
        hits = search(s, "python kubernetes pytorch", embedder=_lexical_embedder, k=2)
    assert isinstance(hits[0], ChunkHit)
    assert "python" in hits[0].chunk_text
    assert hits[0].score >= hits[-1].score  # sorted descending
    assert hits[0].document_title == "eng.md"


def test_search_empty_corpus_returns_empty():
    # The autouse _clear_corpus fixture empties the corpus before each test,
    # so search must hit its no-rows early-return and yield an empty list.
    with Session(engine) as s:
        hits = search(s, "nonexistent zzz", embedder=_lexical_embedder, k=5)
    assert hits == []
