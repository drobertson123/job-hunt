# app/grounding_service.py
"""Grounding verifier: flag artifact sentences unsupported by the corpus.

Embedding-similarity threshold check — NO LLM in the verify path. Each
sentence is embedded (injectable Embedder, same type as corpus_service) and
cosine-matched against all corpus chunks; best score below
``grounding_min_similarity`` -> unsupported -> ``[MISSING]``.

Cosine measures topical closeness, not entailment: this is a review aid that
surfaces low-support spans, not a truth oracle. The human approval step
(`approve_artifact`) is the authority.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass

import numpy as np
from sqlmodel import Session, select

from app.config import get_config
from app.corpus_service import Embedder
from app.models import (
    Artifact,
    Chunk,
    Document,
    GroundingReport,
    ReviewStatus,
    _utcnow,
)


class InvalidStatusTransition(Exception):
    """Raised when an artifact review-status transition is not allowed."""


@dataclass
class Span:
    """A sentence with exact char offsets into the original text."""

    text: str
    start: int
    end: int


# Markdown line prefixes excluded from spans: headings, bullets, numbered
# items, blockquotes. Offsets still index into the original text.
_LINE_PREFIX = re.compile(r"^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s+)?")
# Sentence end: ./!/? followed by whitespace or end-of-line. "3.5" has no
# trailing space after the dot, so decimals never match.
_SENT_END = re.compile(r"[.!?](?=\s|$)")
_ABBREVIATIONS = (
    "e.g.", "i.e.", "etc.", "vs.", "Mr.", "Ms.", "Dr.",
    "Jr.", "Sr.", "Inc.", "Co.", "St.", "No.",
)
# Spans under this many words are skipped (signatures, "Sincerely,", bare
# headings) — a degenerate-input guard, NOT a factual filter (spec decision 3).
_MIN_WORDS = 3


def split_sentences(text: str) -> list[Span]:
    """Deterministic markdown-aware sentence splitter with exact offsets."""
    spans: list[Span] = []
    offset = 0
    for line in text.split("\n"):
        prefix_len = _LINE_PREFIX.match(line).end()
        content = line[prefix_len:]
        base = offset + prefix_len
        seg_start = 0
        for m in _SENT_END.finditer(content):
            if any(content[: m.end()].endswith(a) for a in _ABBREVIATIONS):
                continue
            _emit(spans, base + seg_start, content[seg_start : m.end()])
            seg_start = m.end()
        _emit(spans, base + seg_start, content[seg_start:])
        offset += len(line) + 1  # +1 for the split-away "\n"
    return spans


def _emit(spans: list[Span], start: int, piece: str) -> None:
    stripped = piece.strip()
    if len(stripped.split()) < _MIN_WORDS:
        return
    lead = len(piece) - len(piece.lstrip())
    s = start + lead
    spans.append(Span(text=stripped, start=s, end=s + len(stripped)))
