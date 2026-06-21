"""Communications endpoints — read path + inbound message webhooks."""

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


def _check_token(x_sms_token: str | None, token: str | None) -> None:
    expected = get_config().sms_webhook_token
    if expected and (x_sms_token or token) != expected:
        raise HTTPException(status_code=401, detail="invalid token")


def _naive_utc(dt: datetime | None) -> datetime | None:
    # Normalize a tz-aware timestamp to naive UTC (the schema's convention).
    if dt is not None and dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _record_inbound(
    session: Session,
    *,
    channel: CommChannel,
    sender: str,
    body: str,
    received_at: datetime | None,
    opportunity_id: str | None,
    label: str,
) -> Communication:
    return services.record_communication(
        session,
        direction=CommDirection.inbound,
        channel=channel,
        opportunity_id=opportunity_id,
        subject=f"{label} from {sender}",
        body=body,
        occurred_at=_naive_utc(received_at),
        thread_key=sender,
    )


class SmsInbound(BaseModel):
    model_config = {"populate_by_name": True}

    sender: str = Field(alias="from")
    body: str
    received_at: datetime | None = None
    opportunity_id: str | None = None


class InboundMessage(SmsInbound):
    channel: CommChannel = CommChannel.other


@router.post("/sms")
def inbound_sms(
    payload: SmsInbound,
    token: str | None = None,
    x_sms_token: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Communication:
    _check_token(x_sms_token, token)
    return _record_inbound(
        session,
        channel=CommChannel.sms,
        sender=payload.sender,
        body=payload.body,
        received_at=payload.received_at,
        opportunity_id=payload.opportunity_id,
        label="SMS",
    )


@router.post("/inbound")
def inbound_message(
    payload: InboundMessage,
    token: str | None = None,
    x_sms_token: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Communication:
    _check_token(x_sms_token, token)
    return _record_inbound(
        session,
        channel=payload.channel,
        sender=payload.sender,
        body=payload.body,
        received_at=payload.received_at,
        opportunity_id=payload.opportunity_id,
        label=payload.channel.value,
    )
