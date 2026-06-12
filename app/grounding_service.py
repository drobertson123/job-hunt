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


@dataclass
class SentenceFinding:
    """One scored sentence; persisted as a dict in GroundingReport.findings."""

    text: str
    start: int
    end: int
    score: float
    chunk_id: int | None
    document_title: str | None
    supported: bool


@dataclass
class GroundingResult:
    findings: list[SentenceFinding]
    threshold: float
    embedding_model: str

    @property
    def checked_count(self) -> int:
        return len(self.findings)

    @property
    def unsupported_count(self) -> int:
        return sum(1 for f in self.findings if not f.supported)


def check_grounding(
    session: Session,
    text: str,
    *,
    embedder: Embedder,
    threshold: float | None = None,
) -> GroundingResult:
    """Score every sentence of `text` against the corpus by best cosine match.

    Raises ValueError on an empty corpus: checking against nothing would mark
    everything [MISSING], which is misleading rather than safe.

    Same single-embedding-model assumption as corpus_service.search(): all
    stored chunk vectors share one dimension.
    """
    if threshold is None:
        threshold = get_config().grounding_min_similarity
    rows = session.exec(select(Chunk)).all()
    if not rows:
        raise ValueError("corpus is empty — ingest documents before running a grounding check")

    model = rows[0].embedding_model
    spans = split_sentences(text)
    if not spans:
        return GroundingResult(findings=[], threshold=threshold, embedding_model=model)

    smat = np.asarray(embedder([s.text for s in spans]), dtype=np.float32)
    cmat = np.vstack([np.frombuffer(r.embedding, dtype=np.float32) for r in rows])
    sn = smat / (np.linalg.norm(smat, axis=1, keepdims=True) + 1e-12)
    cn = cmat / (np.linalg.norm(cmat, axis=1, keepdims=True) + 1e-12)
    scores = sn @ cn.T  # (n_sentences, n_chunks)
    best = np.argmax(scores, axis=1)

    titles = {d.id: d.title for d in session.exec(select(Document)).all()}
    findings: list[SentenceFinding] = []
    for i, span in enumerate(spans):
        ci = int(best[i])
        score = float(scores[i, ci])
        chunk = rows[ci]
        findings.append(SentenceFinding(
            text=span.text, start=span.start, end=span.end, score=score,
            chunk_id=chunk.id, document_title=titles.get(chunk.document_id),
            supported=score >= threshold,
        ))
    return GroundingResult(findings=findings, threshold=threshold, embedding_model=model)


def annotate(text: str, findings: list[dict]) -> str:
    """Return a copy of `text` with [MISSING: ...] wrapped around unsupported spans.

    Takes the persisted (dict) form of findings. Applies markers in reverse
    offset order so earlier offsets stay valid. Never mutates stored bodies —
    annotation is always derived.
    """
    out = text
    unsupported = [f for f in findings if not f["supported"]]
    for f in sorted(unsupported, key=lambda f: f["start"], reverse=True):
        out = out[: f["start"]] + f"[MISSING: {out[f['start']:f['end']]}]" + out[f["end"]:]
    return out
