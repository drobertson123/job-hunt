"""Artifacts endpoints (generated deliverables; the canvas renders these)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app import corpus_service, export_service, grounding_service, services
from app.config import get_config
from app.db import get_session
from app.models import Artifact, ArtifactFormat, ArtifactKind, GroundingReport

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


class ArtifactCreate(BaseModel):
    title: str
    body: str = ""
    opportunity_id: str | None = None
    kind: ArtifactKind = ArtifactKind.other
    provenance: str | None = None


@router.get("")
def list_artifacts(
    opportunity_id: str | None = None, session: Session = Depends(get_session)
) -> list[Artifact]:
    stmt = select(Artifact).order_by(Artifact.id.desc())
    if opportunity_id:
        stmt = stmt.where(Artifact.opportunity_id == opportunity_id)
    return list(session.exec(stmt).all())


@router.get("/{artifact_id}")
def get_artifact(artifact_id: int, session: Session = Depends(get_session)) -> Artifact:
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return artifact


@router.post("")
def create_artifact(
    body: ArtifactCreate, session: Session = Depends(get_session)
) -> Artifact:
    """Manual create / new version (also used by in-canvas editing later)."""
    return services.add_artifact(
        session,
        title=body.title,
        body=body.body,
        opportunity_id=body.opportunity_id,
        kind=body.kind,
        provenance=body.provenance or "manual",
    )


# --------------------------------------------------------------------------- #
# Slice C: grounding check + review gate.
# --------------------------------------------------------------------------- #


def _grounding_embedder(session: Session):
    """Indirection point: tests monkeypatch this to inject a fake embedder."""
    return corpus_service.default_embedder(session)


class GroundingOut(BaseModel):
    artifact_id: int
    threshold: float
    embedding_model: str
    checked_count: int
    unsupported_count: int
    findings: list[dict]
    annotated_body: str
    stale: bool
    created_at: datetime


def _grounding_out(artifact: Artifact, report: GroundingReport) -> GroundingOut:
    stale = grounding_service.body_hash(artifact.body) != report.body_hash
    # Stale offsets index a body that no longer exists — never apply them.
    annotated = (
        artifact.body if stale else grounding_service.annotate(artifact.body, report.findings)
    )
    return GroundingOut(
        artifact_id=artifact.id, threshold=report.threshold,
        embedding_model=report.embedding_model,
        checked_count=report.checked_count,
        unsupported_count=report.unsupported_count,
        findings=report.findings, annotated_body=annotated,
        stale=stale, created_at=report.created_at,
    )


@router.post("/{artifact_id}/grounding", response_model=GroundingOut)
def run_grounding(
    artifact_id: int, session: Session = Depends(get_session)
) -> GroundingOut:
    try:
        embedder = _grounding_embedder(session)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        report = grounding_service.run_grounding_check(
            session, artifact_id, embedder=embedder
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # run_grounding_check committed; this re-read gets the post-commit row
    # (refreshed review_status) rather than an expired in-session object.
    artifact = session.get(Artifact, artifact_id)
    return _grounding_out(artifact, report)


@router.get("/{artifact_id}/grounding", response_model=GroundingOut)
def get_grounding(
    artifact_id: int, session: Session = Depends(get_session)
) -> GroundingOut:
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    report = session.exec(
        select(GroundingReport).where(GroundingReport.artifact_id == artifact_id)
    ).first()
    if report is None:
        raise HTTPException(
            status_code=404, detail="no grounding report — run a check first"
        )
    return _grounding_out(artifact, report)


@router.post("/{artifact_id}/approve", response_model=Artifact)
def approve(artifact_id: int, session: Session = Depends(get_session)) -> Artifact:
    try:
        return grounding_service.approve_artifact(session, artifact_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except grounding_service.InvalidStatusTransition as e:
        raise HTTPException(status_code=409, detail=str(e))


# --------------------------------------------------------------------------- #
# Slice E: docx/pdf export + export-time review gate.
# --------------------------------------------------------------------------- #

_MEDIA_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


def _export_renderer():
    """Indirection point: tests monkeypatch this to inject a fake renderer."""
    return export_service.render_with_pandoc


class ExportOut(BaseModel):
    artifact_id: int
    format: str
    file_path: str
    download_url: str


@router.post("/{artifact_id}/export", response_model=ExportOut)
def export_artifact(
    artifact_id: int,
    format: Literal["docx", "pdf"],
    session: Session = Depends(get_session),
) -> ExportOut:
    try:
        result = export_service.export_artifact(
            session, artifact_id, ArtifactFormat(format), renderer=_export_renderer()
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except export_service.ExportNotAllowed as e:
        raise HTTPException(status_code=409, detail=str(e))
    except export_service.RendererUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except export_service.RenderFailed as e:
        raise HTTPException(status_code=500, detail=str(e))
    return ExportOut(
        artifact_id=result.artifact_id,
        format=result.format.value,
        file_path=str(result.path),
        download_url=result.download_url,
    )


@router.get("/{artifact_id}/export/{format}")
def download_export(
    artifact_id: int,
    format: Literal["docx", "pdf"],
    session: Session = Depends(get_session),
) -> FileResponse:
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    path = get_config().exports_dir / f"artifact-{artifact.id}-v{artifact.version}.{format}"
    if not path.exists():
        raise HTTPException(status_code=404, detail="not exported yet — POST first")
    return FileResponse(
        path,
        media_type=_MEDIA_TYPES[format],
        filename=export_service.sanitize_filename(artifact.title, format, artifact.version),
    )
