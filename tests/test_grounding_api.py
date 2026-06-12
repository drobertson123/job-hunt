from __future__ import annotations

import pytest
from sqlmodel import Session

from app import services
from app.corpus_service import ingest_document
from app.db import engine
from app.models import Artifact, DocumentMediaType, DocumentSource

_VOCAB = ["python", "kubernetes", "leadership", "apis"]


def _lexical_embedder(texts):
    return [[float(t.lower().count(w)) for w in _VOCAB] for t in texts]


@pytest.fixture
def fake_embedder(monkeypatch):
    monkeypatch.setattr(
        "app.routers.artifacts._grounding_embedder",
        lambda session: _lexical_embedder,
    )


def _seed() -> int:
    with Session(engine) as s:
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


def test_post_grounding_runs_check(client, fake_embedder):
    aid = _seed()
    r = client.post(f"/api/artifacts/{aid}/grounding")
    assert r.status_code == 200
    data = r.json()
    assert data["checked_count"] == 2
    assert data["unsupported_count"] == 1
    assert "[MISSING: I won a Nobel prize in chemistry.]" in data["annotated_body"]
    assert data["stale"] is False
    # the stored body is never mutated
    assert "[MISSING" not in client.get(f"/api/artifacts/{aid}").json()["body"]


def test_post_grounding_missing_artifact_404(client, fake_embedder):
    assert client.post("/api/artifacts/999999/grounding").status_code == 404


def test_post_grounding_empty_corpus_400(client, fake_embedder):
    with Session(engine) as s:
        aid = services.add_artifact(s, title="x", body="Some body text here.").id
    r = client.post(f"/api/artifacts/{aid}/grounding")
    assert r.status_code == 400
    assert "corpus is empty" in r.json()["detail"]


def test_post_grounding_missing_key_400(client, monkeypatch):
    def _no_key(session):
        raise RuntimeError("OpenAI API key is not configured (Settings or OH_OPENAI_API_KEY).")

    monkeypatch.setattr("app.routers.artifacts._grounding_embedder", _no_key)
    aid = _seed()
    r = client.post(f"/api/artifacts/{aid}/grounding")
    assert r.status_code == 400
    assert "OpenAI API key" in r.json()["detail"]


def test_get_grounding_before_check_404(client, fake_embedder):
    aid = _seed()
    assert client.get(f"/api/artifacts/{aid}/grounding").status_code == 404


def test_get_grounding_missing_artifact_404(client, fake_embedder):
    assert client.get("/api/artifacts/999999/grounding").status_code == 404


def test_get_grounding_reports_stale_after_body_change(client, fake_embedder):
    aid = _seed()
    assert client.post(f"/api/artifacts/{aid}/grounding").status_code == 200
    with Session(engine) as s:
        a = s.get(Artifact, aid)
        a.body = "Completely different body now."
        s.add(a)
        s.commit()
    data = client.get(f"/api/artifacts/{aid}/grounding").json()
    assert data["stale"] is True
    # stale offsets must not be applied to the new body
    assert data["annotated_body"] == "Completely different body now."


def test_approve_flow_and_409(client, fake_embedder):
    aid = _seed()
    assert client.post(f"/api/artifacts/{aid}/approve").status_code == 409  # draft
    client.post(f"/api/artifacts/{aid}/grounding")
    r = client.post(f"/api/artifacts/{aid}/approve")
    assert r.status_code == 200
    assert r.json()["review_status"] == "approved"
    assert client.post(f"/api/artifacts/{aid}/approve").status_code == 409  # again
