from __future__ import annotations

import pytest
from sqlmodel import Session

from app.corpus_service import ingest_document
from app.db import engine
from app.grounding_service import check_grounding
from app.models import DocumentMediaType, DocumentSource

# Deterministic embedder: vocab word-count vectors. Sentences sharing corpus
# vocabulary score high; off-corpus sentences embed to ~zero -> score ~0.
_VOCAB = ["python", "kubernetes", "leadership", "apis"]


def _lexical_embedder(texts):
    return [[float(t.lower().count(w)) for w in _VOCAB] for t in texts]


def _seed_corpus(s: Session):
    ingest_document(
        s, title="resume.md", source_kind=DocumentSource.paste,
        media_type=DocumentMediaType.md,
        data=b"I build python apis and run kubernetes clusters with leadership.",
        embedder=_lexical_embedder,
    )


def test_supported_and_unsupported_sentences():
    text = "I build python apis every day. I won a Nobel prize in chemistry."
    with Session(engine) as s:
        _seed_corpus(s)
        result = check_grounding(s, text, embedder=_lexical_embedder, threshold=0.4)
    assert result.checked_count == 2
    by_text = {f.text: f for f in result.findings}
    supported = by_text["I build python apis every day."]
    fabricated = by_text["I won a Nobel prize in chemistry."]
    assert supported.supported is True
    assert supported.document_title == "resume.md"
    assert supported.chunk_id is not None
    assert fabricated.supported is False
    assert fabricated.score < 0.4
    assert result.unsupported_count == 1


def test_threshold_changes_classification():
    text = "I build python apis every day."
    with Session(engine) as s:
        _seed_corpus(s)
        lenient = check_grounding(s, text, embedder=_lexical_embedder, threshold=0.1)
        strict = check_grounding(s, text, embedder=_lexical_embedder, threshold=0.999)
    assert lenient.findings[0].supported is True
    assert strict.findings[0].supported is False


def test_default_threshold_comes_from_config():
    with Session(engine) as s:
        _seed_corpus(s)
        result = check_grounding(
            s, "I build python apis every day.", embedder=_lexical_embedder
        )
    assert result.threshold == 0.40  # config default from Task 1


def test_empty_corpus_raises():
    with Session(engine) as s:
        with pytest.raises(ValueError, match="corpus is empty"):
            check_grounding(s, "Any text at all here.", embedder=_lexical_embedder)


def test_no_checkable_sentences_yields_empty_findings():
    with Session(engine) as s:
        _seed_corpus(s)
        result = check_grounding(s, "Sincerely,", embedder=_lexical_embedder)
    assert result.findings == []
    assert result.checked_count == 0
    assert result.unsupported_count == 0
