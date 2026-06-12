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
import logging
import re
from dataclasses import asdict, dataclass

import numpy as np
from sqlmodel import Session, select

from app.config import get_config
from app.corpus_service import Embedder, default_embedder
from app.db import engine
from app.models import (
    Artifact,
    ArtifactKind,
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


def body_hash(body: str) -> str:
    """sha256 hex of an artifact body — the staleness key on GroundingReport."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def run_grounding_check(
    session: Session,
    artifact_id: int,
    *,
    embedder: Embedder,
    threshold: float | None = None,
) -> GroundingReport:
    """Check an artifact's body, persist the report (replacing any prior one),
    and move the artifact to needs_review."""
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise LookupError(f"artifact {artifact_id} not found")
    result = check_grounding(session, artifact.body, embedder=embedder, threshold=threshold)

    for old in session.exec(
        select(GroundingReport).where(GroundingReport.artifact_id == artifact_id)
    ).all():
        session.delete(old)
    session.flush()  # push DELETEs before the INSERT to avoid UNIQUE conflict

    report = GroundingReport(
        artifact_id=artifact_id,
        body_hash=body_hash(artifact.body),
        threshold=result.threshold,
        embedding_model=result.embedding_model,
        findings=[asdict(f) for f in result.findings],
        checked_count=result.checked_count,
        unsupported_count=result.unsupported_count,
    )
    session.add(report)
    artifact.review_status = ReviewStatus.needs_review
    artifact.updated_at = _utcnow()
    session.add(artifact)
    session.commit()
    session.refresh(report)
    return report


def approve_artifact(session: Session, artifact_id: int) -> Artifact:
    """needs_review -> approved. Any other starting status is rejected:
    an unchecked draft cannot be approved — that IS the review gate."""
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise LookupError(f"artifact {artifact_id} not found")
    if artifact.review_status != ReviewStatus.needs_review:
        raise InvalidStatusTransition(
            f"cannot approve from status '{artifact.review_status.value}' — "
            "run a grounding check first"
        )
    artifact.review_status = ReviewStatus.approved
    artifact.updated_at = _utcnow()
    session.add(artifact)
    session.commit()
    session.refresh(artifact)
    return artifact


# --------------------------------------------------------------------------- #
# Slice A+D: post-run auto-grounding of generative artifacts.
# --------------------------------------------------------------------------- #

logger = logging.getLogger(__name__)

# Kinds that assert facts about the user — auto-checked after every run.
# Research briefs / fit analyses are about the opportunity, not the corpus,
# so checking them would only produce noise (spec decision).
GENERATIVE_KINDS = (
    ArtifactKind.cv,
    ArtifactKind.cover_letter,
    ArtifactKind.pitch,
    ArtifactKind.outreach,
)


def _auto_embedder(session: Session) -> Embedder:
    """Indirection point: tests monkeypatch this to inject a fake embedder."""
    return default_embedder(session)


def auto_ground_run_artifacts(run_id: str) -> list[int]:
    """Best-effort grounding for generative artifacts created by a run.

    Failures (no OpenAI key, empty corpus) are logged and skipped — the run
    must still succeed; an unchecked artifact simply stays `draft`. Returns
    the artifact ids that were checked.
    """
    with Session(engine) as session:
        ids = list(
            session.exec(
                select(Artifact.id)
                .where(Artifact.run_id == run_id)
                .where(Artifact.kind.in_(GENERATIVE_KINDS))
                .order_by(Artifact.id)
            ).all()
        )
    checked: list[int] = []
    for artifact_id in ids:
        try:
            with Session(engine) as session:
                run_grounding_check(
                    session, artifact_id, embedder=_auto_embedder(session)
                )
            checked.append(artifact_id)
        except Exception as exc:  # noqa: BLE001 — never fail the run
            logger.warning("auto-grounding skipped for artifact %s: %s", artifact_id, exc)
    return checked
