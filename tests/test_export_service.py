"""Gate + orchestration tests — fully offline via a fake renderer."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from app import export_service, grounding_service, services
from app.config import get_config
from app.db import engine
from app.models import Artifact, ArtifactFormat, ArtifactKind, ReviewStatus


def _fake_renderer(body_md: str, format: ArtifactFormat) -> bytes:
    return b"PK-fake" if format == ArtifactFormat.docx else b"%PDF-fake"


def _make_artifact(kind: ArtifactKind, status: ReviewStatus) -> int:
    with Session(engine) as s:
        a = services.add_artifact(s, title="CV — Acme", body="# Hi\n\nBody.", kind=kind)
        a.review_status = status
        s.add(a)
        s.commit()
        return a.id


def _export(aid: int, fmt: ArtifactFormat = ArtifactFormat.docx):
    with Session(engine) as s:
        return export_service.export_artifact(s, aid, fmt, renderer=_fake_renderer)


def test_gate_blocks_unapproved_generative_kinds():
    for status in (ReviewStatus.draft, ReviewStatus.needs_review):
        aid = _make_artifact(ArtifactKind.cv, status)
        with pytest.raises(export_service.ExportNotAllowed):
            _export(aid)


def test_gate_passes_approved_generative_kind():
    aid = _make_artifact(ArtifactKind.cv, ReviewStatus.approved)
    result = _export(aid)
    assert result.path.read_bytes() == b"PK-fake"


def test_non_generative_kinds_export_from_any_status():
    aid = _make_artifact(ArtifactKind.research_brief, ReviewStatus.draft)
    result = _export(aid, ArtifactFormat.pdf)
    assert result.path.read_bytes() == b"%PDF-fake"


def test_gate_matches_grounding_constant():
    # the export gate and the auto-grounding selection must never drift apart
    assert export_service.GENERATIVE_KINDS is grounding_service.GENERATIVE_KINDS


def test_export_writes_deterministic_path_and_updates_row():
    aid = _make_artifact(ArtifactKind.fit_analysis, ReviewStatus.draft)
    result = _export(aid)
    cfg = get_config()
    with Session(engine) as s:
        a = s.get(Artifact, aid)
        expected = cfg.exports_dir / f"artifact-{aid}-v{a.version}.docx"
        assert result.path == expected
        assert result.download_url == f"/api/artifacts/{aid}/export/docx"
        assert a.file_path == str(expected)
        assert a.format == ArtifactFormat.markdown  # body stays canonical


def test_both_formats_coexist_on_disk():
    aid = _make_artifact(ArtifactKind.note, ReviewStatus.draft)
    p1 = _export(aid, ArtifactFormat.docx).path
    p2 = _export(aid, ArtifactFormat.pdf).path
    assert p1.exists() and p2.exists() and p1 != p2


def test_missing_artifact_raises_lookup():
    with pytest.raises(LookupError):
        _export(999999)


def test_markdown_format_rejected():
    aid = _make_artifact(ArtifactKind.note, ReviewStatus.draft)
    with pytest.raises(ValueError):
        _export(aid, ArtifactFormat.markdown)


def test_sanitize_filename():
    f = export_service.sanitize_filename
    assert f("CV — Acme/AI: Staff\nEng", "docx", 3) == "CV — Acme_AI_ Staff Eng v3.docx"
    assert f("", "pdf", 1) == "artifact v1.pdf"
