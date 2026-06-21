"""Communications endpoints — read path + inbound SMS webhook."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from app import services
from app.config import get_config
from app.db import get_session
from app.models import Communication, CommChannel, CommDirection

router = APIRouter(prefix="/api/communications", tags=["communications"])


@router.get("")
def list_communications(
    opportunity_id: str | None = None,
    session: Session = Depends(get_session),
) -> list[Communication]:
    return services.list_communications(session, opportunity_id=opportunity_id)


class SmsInbound(BaseModel):
    model_config = {"populate_by_name": True}

    sender: str = Field(alias="from")
    body: str
    received_at: datetime | None = None
    opportunity_id: str | None = None


@router.post("/sms")
def inbound_sms(
    payload: SmsInbound,
    token: str | None = None,
    x_sms_token: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Communication:
    expected = get_config().sms_webhook_token
    if expected and (x_sms_token or token) != expected:
        raise HTTPException(status_code=401, detail="invalid sms token")
    # Normalize tz-aware timestamps to naive UTC (the schema's convention);
    # a forwarder sending a local-offset time is converted, not just truncated.
    occurred_at = payload.received_at
    if occurred_at is not None and occurred_at.tzinfo is not None:
        occurred_at = occurred_at.astimezone(timezone.utc).replace(tzinfo=None)
    return services.record_communication(
        session,
        direction=CommDirection.inbound,
        channel=CommChannel.sms,
        opportunity_id=payload.opportunity_id,
        subject=f"SMS from {payload.sender}",
        body=payload.body,
        occurred_at=occurred_at,
        thread_key=payload.sender,
    )
