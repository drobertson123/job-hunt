# app/corpus_service.py
"""Corpus/RAG substrate: ingest, chunk, embed, and cosine-search career docs.

Embeddings are stored as float32 BLOBs and searched by brute-force numpy cosine
behind `search()` (swappable to sqlite-vec later). The embedder is injectable so
the default test suite runs offline; the default wraps OpenAI text-embedding-3-small.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from sqlmodel import Session, delete, select

from app import settings_service
from app.config import get_config
from app.models import (
    Chunk,
    Document,
    DocumentMediaType,
    DocumentSource,
)

# An embedder maps a batch of texts to a batch of vectors.
Embedder = Callable[[list[str]], list[list[float]]]


def extract_text(*, data: bytes, media_type: DocumentMediaType) -> str:
    """Extract plain text from raw bytes by media type. Raises ValueError if empty."""
    if media_type in (DocumentMediaType.txt, DocumentMediaType.md):
        text = data.decode("utf-8", errors="replace")
    elif media_type == DocumentMediaType.pdf:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    elif media_type == DocumentMediaType.docx:
        import docx

        document = docx.Document(io.BytesIO(data))
        text = "\n".join(p.text for p in document.paragraphs)
    else:  # pragma: no cover - enum is exhaustive
        raise ValueError(f"unsupported media type: {media_type}")

    text = text.strip()
    if not text:
        raise ValueError("no extractable text in document")
    return text


def chunk_text(text: str, *, size: int = 1000, overlap: int = 150) -> list[str]:
    """Split text into overlapping windows, breaking on a nearby boundary.

    Deterministic and dependency-free so it is trivially testable.
    """
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    n = len(text)
    start = 0
    while start < n:
        end = min(start + size, n)
        if end < n:
            window = text[start:end]
            # Prefer the most semantic boundary available past the window
            # midpoint: paragraph, then line, then sentence, then word.
            for pattern in ("\n\n", "\n", ". ", " "):
                brk = window.rfind(pattern)
                if brk > size // 2:
                    end = start + brk + 1
                    break
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks
