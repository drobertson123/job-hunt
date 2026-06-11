# tests/test_corpus_tool.py
from __future__ import annotations

from sqlmodel import Session

from app.agent.tools import ALL_TOOL_NAMES, search_corpus
from app.corpus_service import ingest_document
from app.db import engine
from app.models import DocumentMediaType, DocumentSource


def _lexical_embedder(texts):
    vocab = ["python", "marketing"]
    return [[float(t.lower().count(w)) for w in vocab] for t in texts]


def test_search_corpus_tool_is_registered():
    assert "mcp__app__search_corpus" in ALL_TOOL_NAMES


async def test_search_corpus_returns_provenance_text(monkeypatch):
    with Session(engine) as s:
        ingest_document(s, title="py.md", source_kind=DocumentSource.paste,
                        media_type=DocumentMediaType.md,
                        data=b"python python backend", embedder=_lexical_embedder)
    # Force the tool to use the deterministic embedder instead of OpenAI.
    monkeypatch.setattr("app.agent.tools._corpus_embedder",
                        lambda session: _lexical_embedder)
    result = await search_corpus.handler({"query": "python", "k": 3})
    text = result["content"][0]["text"]
    assert "py.md" in text and "python" in text


async def test_search_corpus_reports_missing_key_as_error(monkeypatch):
    def _no_key(session):
        raise RuntimeError("OpenAI API key is not configured (Settings or OH_OPENAI_API_KEY).")

    monkeypatch.setattr("app.agent.tools._corpus_embedder", _no_key)
    result = await search_corpus.handler({"query": "python"})
    assert result.get("is_error") is True
    assert "OpenAI API key" in result["content"][0]["text"]
