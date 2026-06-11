# app/corpus_service.py
"""Corpus/RAG substrate: ingest, chunk, embed, and cosine-search career docs.

Embeddings are stored as float32 BLOBs and searched by brute-force numpy cosine
behind `search()` (swappable to sqlite-vec later). The embedder is injectable so
the default test suite runs offline; the default wraps OpenAI text-embedding-3-small.
"""

from __future__ import annotations

import hashlib
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
            brk = max(
                window.rfind("\n\n"), window.rfind("\n"),
                window.rfind(". "), window.rfind(" "),
            )
            if brk > size // 2:
                end = start + brk + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks
