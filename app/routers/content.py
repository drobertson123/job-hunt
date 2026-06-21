"""Content-library endpoints — read + delete (writes go through the agent tool)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session

from app import services
from app.db import get_session
from app.models import ContentBlock, ContentBlockKind

router = APIRouter(prefix="/api/content-blocks", tags=["content-blocks"])


@router.get("")
def list_content_blocks(
    kind: ContentBlockKind | None = None, session: Session = Depends(get_session)
) -> list[ContentBlock]:
    return services.list_content_blocks(session, kind=kind)


@router.delete("/{block_id}", status_code=204)
def delete_content_block(block_id: int, session: Session = Depends(get_session)) -> Response:
    if not services.delete_content_block(session, block_id):
        raise HTTPException(status_code=404, detail="content block not found")
    return Response(status_code=204)
