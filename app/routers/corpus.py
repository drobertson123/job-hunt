# app/routers/corpus.py
"""Corpus endpoints: upload/paste career docs, list/delete, synthesize profile."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ValidationError
from sqlmodel import Session, select

from app import corpus_service
from app.db import get_session
from app.models import Document, DocumentMediaType, DocumentSource, Profile
from app.profile_service import synthesize_profile

router = APIRouter(prefix="/api/corpus", tags=["corpus"])

_EXT_TO_MEDIA = {
    "pdf": DocumentMediaType.pdf, "docx": DocumentMediaType.docx,
    "txt": DocumentMediaType.txt, "md": DocumentMediaType.md,
    "markdown": DocumentMediaType.md,
}


def _embedder_for(session: Session):
    """Indirection point: tests monkeypatch this to inject a fake embedder."""
    return corpus_service.default_embedder(session)


class PasteIn(BaseModel):
    title: str
    text: str


class DocumentOut(BaseModel):
    id: int
    title: str
    source_kind: DocumentSource
    media_type: DocumentMediaType
    char_count: int


# NOTE: paste (JSON) and upload (multipart) MUST be separate routes — FastAPI
# cannot accept a JSON body and File/Form on the same endpoint (Content-Type clash).


@router.post("/documents", response_model=DocumentOut)
def add_pasted_document(
    body: PasteIn,
    session: Session = Depends(get_session),
) -> Document:
    try:
        embedder = _embedder_for(session)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        return corpus_service.ingest_document(
            session, title=body.title, source_kind=DocumentSource.paste,
            media_type=DocumentMediaType.md, data=body.text.encode("utf-8"),
            embedder=embedder,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/documents/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    session: Session = Depends(get_session),
) -> Document:
    try:
        embedder = _embedder_for(session)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    media = _EXT_TO_MEDIA.get(ext)
    if media is None:
        raise HTTPException(status_code=400, detail=f"unsupported file type: .{ext}")
    data = await file.read()
    try:
        return corpus_service.ingest_document(
            session, title=title or file.filename or "upload",
            source_kind=DocumentSource.upload, media_type=media,
            data=data, embedder=embedder,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(session: Session = Depends(get_session)) -> list[Document]:
    return session.exec(select(Document).order_by(Document.created_at.desc())).all()


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, session: Session = Depends(get_session)) -> dict:
    from app.models import Chunk
    from sqlmodel import delete as sql_delete

    doc = session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="not found")
    session.exec(sql_delete(Chunk).where(Chunk.document_id == doc_id))
    session.delete(doc)
    session.commit()
    return {"deleted": doc_id}


@router.post("/profile/synthesize", response_model=Profile)
async def synthesize(session: Session = Depends(get_session)) -> Profile:
    try:
        return await synthesize_profile(session)
    except (ValueError, ValidationError) as e:
        # Empty corpus (ValueError) or malformed model output that fails schema
        # validation — both are client-fixable, not server faults. ValidationError
        # is listed explicitly so the 400 holds even if Pydantic stops subclassing
        # ValueError in a future version.
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/profile", response_model=Profile | None)
def get_profile(session: Session = Depends(get_session)) -> Profile | None:
    return session.exec(select(Profile)).first()
