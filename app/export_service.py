"""Artifact export — render markdown bodies to docx/pdf and gate on review.

The renderer shells out to pandoc (docx natively; pdf via the weasyprint
engine). It is injectable so the orchestration/gate logic tests run fully
offline with a fake. Export is where the slice-C review gate gets teeth:
generative artifact kinds must be `approved` before they can leave the app.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session

from app.config import get_config
from app.grounding_service import GENERATIVE_KINDS
from app.models import Artifact, ArtifactFormat, ReviewStatus, _utcnow

_CSS_PATH = Path(__file__).resolve().parent / "export.css"

EXPORT_FORMATS = (ArtifactFormat.docx, ArtifactFormat.pdf)


class RendererUnavailable(RuntimeError):
    """pandoc or its PDF engine is missing (router -> 503)."""


class RenderFailed(RuntimeError):
    """pandoc exited non-zero on valid-looking input (router -> 500)."""


class ExportNotAllowed(Exception):
    """Generative artifact not approved (router -> 409)."""


def weasyprint_path() -> str | None:
    """The weasyprint executable: venv bin first, then PATH."""
    venv_candidate = Path(sys.executable).parent / "weasyprint"
    if venv_candidate.exists():
        return str(venv_candidate)
    return shutil.which("weasyprint")


def render_with_pandoc(body_md: str, format: ArtifactFormat) -> bytes:
    """Render markdown to docx/pdf bytes via pandoc. Raises on missing tools."""
    if format not in EXPORT_FORMATS:
        raise ValueError(f"not an export format: {format.value}")
    pandoc = shutil.which("pandoc")
    if pandoc is None:
        raise RendererUnavailable("pandoc is not installed (apt-get install pandoc)")

    with tempfile.TemporaryDirectory(prefix="oh-export-") as tmp:
        out_path = Path(tmp) / f"out.{format.value}"
        cmd = [pandoc, "-f", "markdown", "-o", str(out_path)]
        if format == ArtifactFormat.pdf:
            engine = weasyprint_path()
            if engine is None:
                raise RendererUnavailable(
                    "weasyprint is not installed (uv add weasyprint + pango libs)"
                )
            cmd += ["--pdf-engine", engine, "--css", str(_CSS_PATH), "-t", "html5"]
        else:
            cmd += ["-t", "docx"]
        result = subprocess.run(
            cmd, input=body_md.encode("utf-8"), capture_output=True, timeout=120
        )
        if result.returncode != 0:
            tail = result.stderr.decode("utf-8", "replace")[-500:]
            raise RenderFailed(f"pandoc failed for {format.value}: {tail}")
        return out_path.read_bytes()


# --------------------------------------------------------------------------- #
# Orchestration + gate.
# --------------------------------------------------------------------------- #


@dataclass
class ExportResult:
    artifact_id: int
    format: ArtifactFormat
    path: Path
    download_url: str


def sanitize_filename(title: str, ext: str, version: int) -> str:
    """Human filename for Content-Disposition; titles come from agent output."""
    clean = re.sub(r"[\\/:\0]", "_", title)
    clean = re.sub(r"[\r\n\t]+", " ", clean)
    clean = re.sub(r"[\x00-\x1f]", "", clean).strip() or "artifact"
    clean = clean[:120]
    return f"{clean} v{version}.{ext}"


def export_artifact(
    session: Session,
    artifact_id: int,
    format: ArtifactFormat,
    *,
    renderer=render_with_pandoc,
) -> ExportResult:
    """Render an artifact's body and persist it under exports_dir.

    The review gate: generative kinds (same constant the post-run
    auto-grounding uses) must be `approved` — export is where review-before-
    send is enforced. Other kinds are internal documents and export freely.
    """
    if format not in EXPORT_FORMATS:
        raise ValueError(f"not an export format: {format.value}")
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise LookupError(f"artifact {artifact_id} not found")
    if artifact.kind in GENERATIVE_KINDS and artifact.review_status != ReviewStatus.approved:
        raise ExportNotAllowed(
            f"artifact {artifact_id} is {artifact.review_status.value}; "
            "generative artifacts must be approved before export — run the "
            "grounding check and approve it first"
        )

    data = renderer(artifact.body, format)
    cfg = get_config()
    path = cfg.exports_dir / f"artifact-{artifact.id}-v{artifact.version}.{format.value}"
    path.write_bytes(data)

    artifact.file_path = str(path)  # informational: latest export
    artifact.updated_at = _utcnow()
    session.add(artifact)
    session.commit()
    return ExportResult(
        artifact_id=artifact_id,
        format=format,
        path=path,
        download_url=f"/api/artifacts/{artifact_id}/export/{format.value}",
    )
