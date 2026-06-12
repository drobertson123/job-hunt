from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app import services
from app.corpus_service import ingest_document
from app.db import engine
from app.grounding_service import (
    InvalidStatusTransition,
    approve_artifact,
    run_grounding_check,
)
from app.models import (
    Artifact,
    DocumentMediaType,
    DocumentSource,
    GroundingReport,
    ReviewStatus,
)

_VOCAB = ["python", "kubernetes", "leadership", "apis"]


def _lexical_embedder(texts):
    return [[float(t.lower().count(w)) for w in _VOCAB] for t in texts]


def _seed(s: Session) -> int:
    ingest_document(
        s, title="resume.md", source_kind=DocumentSource.paste,
        media_type=DocumentMediaType.md,
        data=b"I build python apis and run kubernetes clusters with leadership.",
        embedder=_lexical_embedder,
    )
    a = services.add_artifact(
        s, title="cover letter",
        body="I build python apis every day. I won a Nobel prize in chemistry.",
    )
    return a.id


def test_check_persists_report_and_sets_needs_review():
    with Session(engine) as s:
        aid = _seed(s)
        report = run_grounding_check(s, aid, embedder=_lexical_embedder)
        artifact = s.get(Artifact, aid)
    assert artifact.review_status == ReviewStatus.needs_review
    assert report.artifact_id == aid
    assert report.checked_count == 2
    assert report.unsupported_count == 1
    assert len(report.body_hash) == 64  # sha256 hex


def test_recheck_replaces_report_not_duplicates():
    with Session(engine) as s:
        aid = _seed(s)
        run_grounding_check(s, aid, embedder=_lexical_embedder)
        run_grounding_check(s, aid, embedder=_lexical_embedder)
        reports = s.exec(
            select(GroundingReport).where(GroundingReport.artifact_id == aid)
        ).all()
    assert len(reports) == 1


def test_approve_only_from_needs_review():
    with Session(engine) as s:
        aid = _seed(s)
        with pytest.raises(InvalidStatusTransition):
            approve_artifact(s, aid)  # still draft: unchecked -> cannot approve
        run_grounding_check(s, aid, embedder=_lexical_embedder)
        artifact = approve_artifact(s, aid)
        assert artifact.review_status == ReviewStatus.approved
        with pytest.raises(InvalidStatusTransition):
            approve_artifact(s, aid)  # already approved


def test_new_version_starts_at_draft():
    with Session(engine) as s:
        aid = _seed(s)
        run_grounding_check(s, aid, embedder=_lexical_embedder)
        approve_artifact(s, aid)
        v2 = services.add_artifact(s, title="cover letter", body="New body text here.")
    assert v2.version == 2
    assert v2.id != aid
    assert v2.review_status == ReviewStatus.draft


def test_check_missing_artifact_raises_lookup_error():
    with Session(engine) as s:
        with pytest.raises(LookupError):
            run_grounding_check(s, 999_999, embedder=_lexical_embedder)


def test_custom_threshold_flows_into_persisted_report():
    with Session(engine) as s:
        aid = _seed(s)
        report = run_grounding_check(
            s, aid, embedder=_lexical_embedder, threshold=0.99
        )
    assert report.threshold == 0.99
    assert report.unsupported_count == 2  # near-1.0 fails both sentences


def test_recheck_after_approval_returns_to_needs_review():
    with Session(engine) as s:
        aid = _seed(s)
        run_grounding_check(s, aid, embedder=_lexical_embedder)
        approve_artifact(s, aid)
        run_grounding_check(s, aid, embedder=_lexical_embedder)
        artifact = s.get(Artifact, aid)
    assert artifact.review_status == ReviewStatus.needs_review
