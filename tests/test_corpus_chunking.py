# tests/test_corpus_chunking.py
from __future__ import annotations

from app.corpus_service import chunk_text


def test_chunk_empty_returns_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_chunk_short_text_is_single_chunk():
    assert chunk_text("one short paragraph") == ["one short paragraph"]


def test_chunk_long_text_splits_with_overlap():
    text = " ".join(f"word{i}" for i in range(1000))  # ~6-7k chars
    chunks = chunk_text(text, size=1000, overlap=150)
    assert len(chunks) > 1
    assert all(len(c) <= 1000 for c in chunks)
    # overlap: end of chunk 0 reappears at the start of chunk 1
    tail = chunks[0][-50:]
    assert tail.split()[-1] in chunks[1]


def test_chunk_is_deterministic():
    text = "para one.\n\n" + ("alpha beta gamma " * 200)
    assert chunk_text(text) == chunk_text(text)
