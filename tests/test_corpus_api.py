# tests/test_corpus_api.py
from __future__ import annotations

import app.routers.corpus as corpus_router
from app.models import DocumentMediaType


def _lexical_embedder(texts):
    return [[float(t.lower().count("python")), 1.0] for t in texts]


def test_paste_list_and_delete(client, monkeypatch):
    monkeypatch.setattr(corpus_router, "_embedder_for",
                        lambda session: _lexical_embedder)
    # paste a document
    r = client.post("/api/corpus/documents",
                    json={"title": "note.md", "text": "python python engineer"})
    assert r.status_code == 200, r.text
    doc_id = r.json()["id"]

    # it shows up in the list (without embeddings)
    listed = client.get("/api/corpus/documents").json()
    assert any(d["id"] == doc_id for d in listed)

    # delete it
    assert client.delete(f"/api/corpus/documents/{doc_id}").status_code == 200
    listed2 = client.get("/api/corpus/documents").json()
    assert all(d["id"] != doc_id for d in listed2)


def test_synthesize_and_get_profile(client, monkeypatch):
    monkeypatch.setattr(corpus_router, "_embedder_for",
                        lambda session: _lexical_embedder)

    async def fake_synth(session, *, query_fn=None):
        from app.models import Profile
        from sqlmodel import select
        row = session.exec(select(Profile)).first() or Profile()
        row.headline = "Synthesized"
        row.skills = ["python"]
        session.add(row); session.commit(); session.refresh(row)
        return row

    monkeypatch.setattr(corpus_router, "synthesize_profile", fake_synth)

    client.post("/api/corpus/documents", json={"title": "cv.md", "text": "python dev"})
    r = client.post("/api/corpus/profile/synthesize")
    assert r.status_code == 200, r.text
    assert r.json()["headline"] == "Synthesized"

    g = client.get("/api/corpus/profile")
    assert g.status_code == 200 and g.json()["skills"] == ["python"]
