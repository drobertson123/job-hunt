# tests/test_corpus_extract.py
from __future__ import annotations

from pathlib import Path

import pytest

from app.corpus_service import extract_text
from app.models import DocumentMediaType

FIX = Path(__file__).parent / "fixtures" / "corpus"


def test_extract_md_and_txt():
    md = extract_text(data=(FIX / "sample.md").read_bytes(), media_type=DocumentMediaType.md)
    assert "Jane Doe" in md and "MLOps" in md
    txt = extract_text(data=(FIX / "sample.txt").read_bytes(), media_type=DocumentMediaType.txt)
    assert "ML engineer" in txt


def test_extract_docx():
    out = extract_text(data=(FIX / "sample.docx").read_bytes(), media_type=DocumentMediaType.docx)
    assert "Jane Doe" in out and "PyTorch" in out


def test_extract_pdf():
    out = extract_text(data=(FIX / "sample.pdf").read_bytes(), media_type=DocumentMediaType.pdf)
    assert "Jane Doe" in out


def test_extract_empty_raises():
    with pytest.raises(ValueError):
        extract_text(data=b"   ", media_type=DocumentMediaType.txt)
