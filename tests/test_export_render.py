"""Real-render smoke tests — exercise actual pandoc (+ weasyprint for pdf).

These run by default on this machine and self-skip where the toolchain is
absent, so CI-without-pandoc stays green.
"""

from __future__ import annotations

import shutil

import pytest

from app.export_service import RendererUnavailable, render_with_pandoc, weasyprint_path
from app.models import ArtifactFormat

SAMPLE_MD = (
    "# Fit analysis — Acme AI\n\n"
    "Some **bold** intro paragraph.\n\n"
    "- first bullet\n- second bullet\n\n"
    "| dim | score |\n|---|---|\n| skills | 4 |\n"
)

needs_pandoc = pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")
needs_weasyprint = pytest.mark.skipif(weasyprint_path() is None, reason="weasyprint not installed")


@needs_pandoc
def test_docx_renders_real_bytes():
    out = render_with_pandoc(SAMPLE_MD, ArtifactFormat.docx)
    assert out[:2] == b"PK"  # docx is a zip container
    assert len(out) > 1000


@needs_pandoc
@needs_weasyprint
def test_pdf_renders_real_bytes():
    out = render_with_pandoc(SAMPLE_MD, ArtifactFormat.pdf)
    assert out[:4] == b"%PDF"
    assert len(out) > 1000


@needs_pandoc
def test_markdown_is_not_a_render_target():
    with pytest.raises(ValueError):
        render_with_pandoc(SAMPLE_MD, ArtifactFormat.markdown)


def test_missing_pandoc_raises_unavailable(monkeypatch):
    monkeypatch.setattr("app.export_service.shutil.which", lambda name: None)
    with pytest.raises(RendererUnavailable):
        render_with_pandoc(SAMPLE_MD, ArtifactFormat.docx)
