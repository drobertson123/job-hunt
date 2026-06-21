# Generalize Inbound Webhook to Any Channel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept inbound messages from any channel (WhatsApp, LinkedIn, SMS, …) through one webhook so an Android notification-forwarder can route them all into the app; they surface in Attention exactly like captured SMS.

**Architecture:** Add a `whatsapp` value to `CommChannel`; add `POST /api/communications/inbound` (channel-parameterized) alongside the existing `/sms`, both sharing token + tz-normalize helpers and the `record_communication` service. No schema migration (channel is a VARCHAR enum).

**Tech Stack:** FastAPI, SQLModel/SQLite, pytest.

## Global Constraints
- Reuse `record_communication` (Constitution II). Naive-UTC datetimes; convert tz-aware `received_at` via `.astimezone(timezone.utc).replace(tzinfo=None)`.
- The optional token is the existing `config.sms_webhook_token` (now the general inbound secret); default None → open.
- The existing `POST /api/communications/sms` must keep working unchanged (back-compat with the already-shipped Android doc).
- pytest: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest …`. Verify: `bash scripts/ci/gate.sh` GREEN.
- Do NOT invoke any finishing/branch skill — stop after committing and reporting.

---

### Task 1: `whatsapp` channel + general `/inbound` endpoint

**Files:**
- Modify: `app/models.py` (`CommChannel.whatsapp`)
- Modify: `app/routers/communications.py` (general endpoint + DRY helpers)
- Modify: `docs/sms-forwarding-android.md` (mention the general endpoint + WhatsApp/LinkedIn notification forwarding)
- Test: `tests/test_inbound_webhook.py`

- [ ] **Step 1: Add the channel value**

In `app/models.py`, in `class CommChannel`, add after `linkedin = "linkedin"`:
```python
    whatsapp = "whatsapp"
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_inbound_webhook.py`:
```python
def test_inbound_whatsapp_message(client):
    r = client.post(
        "/api/communications/inbound",
        json={"from": "Sarah (KORE1)", "body": "Sent you the JD on WhatsApp", "channel": "whatsapp"},
    )
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["channel"] == "whatsapp"
    assert c["direction"] == "inbound"
    assert c["thread_key"] == "Sarah (KORE1)"


def test_inbound_linkedin_message(client):
    r = client.post(
        "/api/communications/inbound",
        json={"from": "recruiter", "body": "Are you open to a chat?", "channel": "linkedin"},
    )
    assert r.status_code == 200
    assert r.json()["channel"] == "linkedin"


def test_inbound_defaults_to_other_and_rejects_bad_channel(client):
    ok = client.post("/api/communications/inbound", json={"from": "x", "body": "y"})
    assert ok.status_code == 200 and ok.json()["channel"] == "other"
    bad = client.post(
        "/api/communications/inbound",
        json={"from": "x", "body": "y", "channel": "carrier-pigeon"},
    )
    assert bad.status_code == 422  # not a valid CommChannel


def test_inbound_token_enforced_when_set(client, monkeypatch):
    from app.config import get_config

    monkeypatch.setattr(get_config(), "sms_webhook_token", "k", raising=False)
    assert client.post(
        "/api/communications/inbound", json={"from": "x", "body": "y"}
    ).status_code == 401
    assert client.post(
        "/api/communications/inbound",
        json={"from": "x", "body": "y"},
        headers={"X-SMS-Token": "k"},
    ).status_code == 200


def test_sms_endpoint_still_works(client):
    r = client.post("/api/communications/sms", json={"from": "+1", "body": "hi"})
    assert r.status_code == 200 and r.json()["channel"] == "sms"
```

- [ ] **Step 3: Run it to verify it fails**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_inbound_webhook.py -q`
Expected: FAIL (`/inbound` route absent → 404/405).

- [ ] **Step 4: Implement the general endpoint + DRY the helpers**

In `app/routers/communications.py`, add the helpers and the general endpoint, and refactor `/sms` to use the helpers. The file becomes:
```python
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
```

- [ ] **Step 5: Run the test + full gate**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_inbound_webhook.py -q` → PASS
Then `bash scripts/ci/gate.sh` → GATE PASSED.

- [ ] **Step 6: Update the Android doc**

In `docs/sms-forwarding-android.md`, add a short section after the SMS endpoint describing the general endpoint:
```markdown
## Other channels (WhatsApp, LinkedIn, …) via notification forwarding

Android notification-listener automations (MacroDroid: *Notification Received*;
Tasker: *Notification* event) can capture WhatsApp / LinkedIn message previews
and POST them to the general endpoint:

    POST http://<tailscale-ip>:8000/api/communications/inbound
    { "from": "<sender or app>", "body": "<notification text>", "channel": "whatsapp" }

`channel` is one of `whatsapp · linkedin · sms · email · phone · other`. These are
notification *previews* (often truncated), not full threads — but they land in
**Attention → Untriaged messages** for triage like any inbound message. The same
optional `X-SMS-Token` / `?token=` applies.
```

- [ ] **Step 7: Commit**

```bash
git add app/models.py app/routers/communications.py tests/test_inbound_webhook.py docs/sms-forwarding-android.md
git commit -m "feat(inbound): generalize webhook to any channel (+ whatsapp); notification-forwarding for WhatsApp/LinkedIn"
```
