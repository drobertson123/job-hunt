"""Artifacts endpoints (generated deliverables; the canvas renders these)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app import services
from app.db import get_session
from app.models import Artifact, ArtifactKind

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
