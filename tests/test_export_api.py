"""Export endpoint tests — offline via monkeypatched renderer."""

from __future__ import annotations

from sqlmodel import Session

from app import export_service, services
from app.db import engine
from app.models import ArtifactFormat, ArtifactKind, ReviewStatus


def _fake_renderer(body_md: str, format: ArtifactFormat) -> bytes:
    return b"PK-fake" if format == ArtifactFormat.docx else b"%PDF-fake"


def _patch_renderer(monkeypatch, fn=_fake_renderer):
    monkeypatch.setattr("app.routers.artifacts._export_renderer", lambda: fn)


def _make_artifact(kind=ArtifactKind.note, status=ReviewStatus.draft, title="Doc") -> int:
    with Session(engine) as s:
        a = services.add_artifact(s, title=title, body="# Hi\n\nBody.", kind=kind)
        a.review_status = status
        s.add(a)
        s.commit()
        return a.id


def test_post_then_get_roundtrip(client, monkeypatch):
    _patch_renderer(monkeypatch)
    aid = _make_artifact()
    r = client.post(f"/api/artifacts/{aid}/export?format=docx")
    assert r.status_code == 200
    body = r.json()
    assert body["download_url"] == f"/api/artifacts/{aid}/export/docx"
    dl = client.get(body["download_url"])
    assert dl.status_code == 200
    assert dl.content == b"PK-fake"
    assert "attachment" in dl.headers["content-disposition"]
    assert dl.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )


def test_pdf_media_type(client, monkeypatch):
    _patch_renderer(monkeypatch)
    aid = _make_artifact()
    client.post(f"/api/artifacts/{aid}/export?format=pdf")
    dl = client.get(f"/api/artifacts/{aid}/export/pdf")
    assert dl.headers["content-type"] == "application/pdf"
    assert dl.content == b"%PDF-fake"


def test_gate_409_with_actionable_detail(client, monkeypatch):
    _patch_renderer(monkeypatch)
    aid = _make_artifact(kind=ArtifactKind.cv, status=ReviewStatus.draft)
    r = client.post(f"/api/artifacts/{aid}/export?format=docx")
    assert r.status_code == 409
    assert "approve" in r.json()["detail"]


def test_invalid_format_422(client, monkeypatch):
    _patch_renderer(monkeypatch)
    aid = _make_artifact()
    assert client.post(f"/api/artifacts/{aid}/export?format=markdown").status_code == 422
    assert client.post(f"/api/artifacts/{aid}/export?format=odt").status_code == 422


def test_missing_artifact_404(client, monkeypatch):
    _patch_renderer(monkeypatch)
    assert client.post("/api/artifacts/999999/export?format=docx").status_code == 404
    assert client.get("/api/artifacts/999999/export/docx").status_code == 404


def test_get_before_post_404(client, monkeypatch):
    _patch_renderer(monkeypatch)
    aid = _make_artifact()
    assert client.get(f"/api/artifacts/{aid}/export/docx").status_code == 404


def test_renderer_unavailable_503(client, monkeypatch):
    def broken(body_md, format):
        raise export_service.RendererUnavailable("pandoc is not installed")

    _patch_renderer(monkeypatch, broken)
    aid = _make_artifact()
    r = client.post(f"/api/artifacts/{aid}/export?format=docx")
    assert r.status_code == 503
    assert "pandoc" in r.json()["detail"]


def test_render_failure_500(client, monkeypatch):
    def broken(body_md, format):
        raise export_service.RenderFailed("pandoc failed: boom")

    _patch_renderer(monkeypatch, broken)
    aid = _make_artifact()
    assert client.post(f"/api/artifacts/{aid}/export?format=docx").status_code == 500
