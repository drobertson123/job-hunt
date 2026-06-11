# tests/test_corpus_embedder.py
from __future__ import annotations

import pytest
from sqlmodel import Session

from app.corpus_service import default_embedder
from app.db import engine


def test_default_embedder_without_key_raises_clear_error(monkeypatch):
    # No OpenAI key configured in the test settings table; guard against an
    # ambient OH_OPENAI_API_KEY leaking in from the developer/CI environment.
    monkeypatch.delenv("OH_OPENAI_API_KEY", raising=False)
    with Session(engine) as s:
        with pytest.raises(RuntimeError, match="OpenAI API key"):
            default_embedder(s)
