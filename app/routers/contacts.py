"""Contacts endpoints — list + create (manual add). The agent also writes via the tool."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app import services
from app.db import get_session
from app.models import Contact

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


class ContactCreate(BaseModel):
    name: str
    opportunity_id: str | None = None
    role: str | None = None
    organization: str | None = None
    link: str | None = None
    notes: str = ""


@router.get("")
def list_contacts(
    opportunity_id: str | None = None,
    session: Session = Depends(get_session),
) -> list[Contact]:
    return services.list_contacts(session, opportunity_id=opportunity_id)


@router.post("")
def create_contact(body: ContactCreate, session: Session = Depends(get_session)) -> Contact:
    return services.add_contact(
        session,
        name=body.name,
        opportunity_id=body.opportunity_id,
        role=body.role,
        organization=body.organization,
        link=body.link,
        notes=body.notes,
    )
