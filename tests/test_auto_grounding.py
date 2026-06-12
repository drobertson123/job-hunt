"""Post-run auto-grounding: generative artifacts from a run get checked and
land needs_review; everything else (and every failure mode) stays draft."""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app import grounding_service, services
from app.agent import runner
from app.corpus_service import ingest_document
from app.db import engine
from app.models import (
    Artifact,
    ArtifactKind,
    DocumentMediaType,
    DocumentSource,
    GroundingReport,
    ReviewStatus,
)

_VOCAB = ["python", "kubernetes", "leadership", "apis"]


def _lexical_embedder(texts):
    return [[float(t.lower().count(w)) for w in _VOCAB] for t in texts]


@pytest.fixture
def fake_auto_embedder(monkeypatch):
    monkeypatch.setattr(
        "app.grounding_service._auto_embedder", lambda session: _lexical_embedder
    )


def _seed_corpus():
    with Session(engine) as s:
        ingest_document(
            s, title="resume.md", source_kind=DocumentSource.paste,
            media_type=DocumentMediaType.md,
            data=b"I build python apis and run kubernetes clusters with leadership.",
            embedder=_lexical_embedder,
        )


def _make_artifact(kind: ArtifactKind, run_id: str | None) -> int:
    with Session(engine) as s:
        a = services.add_artifact(
            s, title="t",
            body="I build python apis daily. I won a Nobel prize in chemistry.",
            kind=kind, run_id=run_id,
        )
        return a.id


def test_generative_artifact_gets_checked(fake_auto_embedder):
    _seed_corpus()
    run = runner.create_run("x", model=None)
    aid = _make_artifact(ArtifactKind.cv, run.id)
    assert grounding_service.auto_ground_run_artifacts(run.id) == [aid]
    with Session(engine) as s:
        assert s.get(Artifact, aid).review_status == ReviewStatus.needs_review
        report = s.exec(
            select(GroundingReport).where(GroundingReport.artifact_id == aid)
        ).one()
        assert report.unsupported_count >= 1  # the Nobel prize sentence


def test_non_generative_kinds_stay_draft(fake_auto_embedder):
    _seed_corpus()
    run = runner.create_run("x", model=None)
    aid = _make_artifact(ArtifactKind.research_brief, run.id)
    assert grounding_service.auto_ground_run_artifacts(run.id) == []
    with Session(engine) as s:
        assert s.get(Artifact, aid).review_status == ReviewStatus.draft


def test_failure_is_non_fatal(fake_auto_embedder):
    # empty corpus -> check_grounding raises ValueError -> skipped, stays draft
    run = runner.create_run("x", model=None)
    aid = _make_artifact(ArtifactKind.cv, run.id)
    assert grounding_service.auto_ground_run_artifacts(run.id) == []
    with Session(engine) as s:
        assert s.get(Artifact, aid).review_status == ReviewStatus.draft
        assert s.exec(
            select(GroundingReport).where(GroundingReport.artifact_id == aid)
        ).first() is None


def test_other_runs_artifacts_untouched(fake_auto_embedder):
    _seed_corpus()
    run_a = runner.create_run("a", model=None)
    run_b = runner.create_run("b", model=None)
    aid_b = _make_artifact(ArtifactKind.cv, run_b.id)
    assert grounding_service.auto_ground_run_artifacts(run_a.id) == []
    with Session(engine) as s:
        assert s.get(Artifact, aid_b).review_status == ReviewStatus.draft


def test_one_failure_does_not_stop_other_checks(fake_auto_embedder, monkeypatch):
    _seed_corpus()
    run = runner.create_run("x", model=None)
    aid_bad = _make_artifact(ArtifactKind.cv, run.id)
    aid_good = _make_artifact(ArtifactKind.cover_letter, run.id)

    real_check = grounding_service.run_grounding_check

    def flaky_check(session, artifact_id, **kwargs):
        if artifact_id == aid_bad:
            raise RuntimeError("boom")
        return real_check(session, artifact_id, **kwargs)

    monkeypatch.setattr(grounding_service, "run_grounding_check", flaky_check)
    assert grounding_service.auto_ground_run_artifacts(run.id) == [aid_good]
    with Session(engine) as s:
        assert s.get(Artifact, aid_bad).review_status == ReviewStatus.draft
        assert s.get(Artifact, aid_good).review_status == ReviewStatus.needs_review


from claude_agent_sdk import ResultMessage  # noqa: E402


def _fake_agent():
    async def fake(*, prompt, options):  # noqa: ARG001
        yield ResultMessage(
            subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
            num_turns=1, session_id="sess", result="ok", total_cost_usd=0.0,
        )

    return fake


async def test_stream_run_auto_grounds_on_completion(fake_auto_embedder):
    _seed_corpus()
    run = runner.create_run("tailor my cv", model=None)
    # Simulates the artifact a skill saved mid-run (attributed via run_id).
    aid = _make_artifact(ArtifactKind.cv, run.id)
    events = [
        e async for e in runner.stream_run("tailor my cv", run=run, query_fn=_fake_agent())
    ]
    assert events[-1]["type"] == "status"
    assert events[-1]["content"] == "completed"
    with Session(engine) as s:
        assert s.get(Artifact, aid).review_status == ReviewStatus.needs_review
