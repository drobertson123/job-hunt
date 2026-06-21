# SMS Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest Android SMS into the app — a webhook to capture texts, surface untriaged inbound messages in Attention, and an `sms-analyser` capability for triage.

**Architecture:** `POST /api/communications/sms` writes an inbound `sms` Communication via the existing `record_communication` service; `needs_attention` gains an `untriaged_message` bucket (unlinked inbound comms); a career-pack `sms-analyser` skill mirrors `email-analyser`.

**Tech Stack:** FastAPI, SQLModel/SQLite, the authored career-pack plugin, Next.js/Tailwind (one line), pytest.

## Global Constraints
- Reuse `record_communication` (Constitution II) — no new write path. Datetimes naive UTC (`.replace(tzinfo=None)` on inbound ISO).
- Webhook auth is OPTIONAL: `config.sms_webhook_token` default `None` → no check (matches the app's Tailscale-only no-auth posture); when set, require it via `X-SMS-Token` header or `?token=` query, else 401.
- pytest: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest …`. Frontend: `npm --prefix frontend install` then `npm --prefix frontend run build`.
- Verification: `bash scripts/ci/gate.sh` GREEN; frontend build succeeds.
- Do NOT invoke any finishing/branch skill — stop after committing and reporting.

---

### Task 1: SMS webhook endpoint

**Files:**
- Modify: `app/config.py` (token knob)
- Modify: `app/routers/communications.py` (POST /sms)
- Test: `tests/test_sms_webhook.py`

- [ ] **Step 1: Add the config knob**

In `app/config.py`, after `daily_search_poll_seconds`, add:
```python
    # Optional shared secret for the inbound SMS webhook (None = no auth).
    sms_webhook_token: str | None = None
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_sms_webhook.py`:
```python
from app.config import get_config


def test_sms_webhook_creates_inbound_communication(client):
    r = client.post(
        "/api/communications/sms",
        json={"from": "+15551234567", "body": "Hi, are you free Tue for a call?"},
    )
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["channel"] == "sms"
    assert c["direction"] == "inbound"
    assert c["thread_key"] == "+15551234567"
    assert "free Tue" in c["body"]

    # it shows up in the communications list
    assert any(x["id"] == c["id"] for x in client.get("/api/communications").json())


def test_sms_webhook_token_enforced_when_set(client, monkeypatch):
    monkeypatch.setattr(get_config(), "sms_webhook_token", "s3cret", raising=False)
    # missing/wrong token → 401
    assert client.post(
        "/api/communications/sms", json={"from": "+1", "body": "x"}
    ).status_code == 401
    assert client.post(
        "/api/communications/sms?token=nope", json={"from": "+1", "body": "x"}
    ).status_code == 401
    # correct token via query
    assert client.post(
        "/api/communications/sms?token=s3cret", json={"from": "+1", "body": "x"}
    ).status_code == 200
    # correct token via header
    assert client.post(
        "/api/communications/sms",
        json={"from": "+1", "body": "x"},
        headers={"X-SMS-Token": "s3cret"},
    ).status_code == 200
```
(Note: `get_config()` returns a cached singleton, so `monkeypatch.setattr` on it affects the endpoint's `get_config()` too.)

- [ ] **Step 3: Run it to verify it fails**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_sms_webhook.py -q`
Expected: FAIL (405/404 — endpoint absent).

- [ ] **Step 4: Implement the endpoint**

Replace `app/routers/communications.py` with:
```python
"""Communications endpoints — read path + inbound SMS webhook."""

from __future__ import annotations

from datetime import datetime

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
    return services.record_communication(
        session,
        direction=CommDirection.inbound,
        channel=CommChannel.sms,
        opportunity_id=payload.opportunity_id,
        subject=f"SMS from {payload.sender}",
        body=payload.body,
        occurred_at=payload.received_at.replace(tzinfo=None) if payload.received_at else None,
        thread_key=payload.sender,
    )
```

- [ ] **Step 5: Run the test + full gate**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_sms_webhook.py -q` → PASS
Then `bash scripts/ci/gate.sh` → GATE PASSED.

- [ ] **Step 6: Commit**

```bash
git add app/config.py app/routers/communications.py tests/test_sms_webhook.py
git commit -m "feat(sms): inbound SMS webhook (POST /api/communications/sms) with optional token"
```

---

### Task 2: Surface untriaged inbound messages in Attention

**Files:**
- Modify: `app/orchestration.py` (`needs_attention` — new bucket)
- Modify: `frontend/app/components/AttentionTab.tsx` (one GROUPS line)
- Test: `tests/test_attention*` (add a case; create `tests/test_attention_messages.py` if no attention test file exists)

**Interfaces:**
- Produces: items of `kind="untriaged_message"` + `counts.untriaged_messages` in the `needs_attention` dict.

- [ ] **Step 1: Write the failing test**

Create `tests/test_attention_messages.py`:
```python
from sqlmodel import Session

from app.db import engine
from app import services
from app.models import CommChannel, CommDirection, Opportunity, OpportunityType
from app.orchestration import needs_attention


def test_unlinked_inbound_message_surfaces_in_attention():
    with Session(engine) as s:
        services.record_communication(
            s, direction=CommDirection.inbound, channel=CommChannel.sms,
            subject="SMS from +1", body="call me",
        )  # unlinked → should surface
        att = needs_attention(s)
    msgs = [i for i in att["items"] if i["kind"] == "untriaged_message"]
    assert len(msgs) == 1
    assert att["counts"]["untriaged_messages"] == 1


def test_linked_inbound_message_does_not_surface():
    with Session(engine) as s:
        o = Opportunity(type=OpportunityType.job, title="Linked")
        s.add(o); s.commit(); s.refresh(o)
        services.record_communication(
            s, direction=CommDirection.inbound, channel=CommChannel.sms,
            opportunity_id=o.id, subject="SMS", body="hi",
        )
        att = needs_attention(s)
    assert all(i["kind"] != "untriaged_message" for i in att["items"])
```

- [ ] **Step 2: Run it to verify it fails**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_attention_messages.py -q`
Expected: FAIL (no `untriaged_message` items / KeyError on the count).

- [ ] **Step 3: Implement the bucket**

In `app/orchestration.py`: ensure `CommDirection` is imported from `app.models` (add it to the existing models import). After the `overdue_followups` loop (before the `return`), add:
```python
    untriaged_messages = session.exec(
        select(Communication).where(
            Communication.direction == CommDirection.inbound,
            Communication.opportunity_id.is_(None),
        )
    ).all()
    for c in untriaged_messages:
        items.append(
            {
                "kind": "untriaged_message",
                "severity": "medium",
                "communication_id": c.id,
                "opportunity_id": None,
                "title": c.subject or f"{c.channel.value} message",
                "channel": c.channel.value,
                "occurred_at": c.occurred_at.isoformat(),
                "reason": "Inbound message not yet linked to an opportunity",
            }
        )
```
Then add to the `counts` dict (before `"total"`):
```python
            "untriaged_messages": len(untriaged_messages),
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_attention_messages.py -q`
Expected: PASS.

- [ ] **Step 5: Add the Attention group + build the frontend**

In `frontend/app/components/AttentionTab.tsx`, add to the `GROUPS` array (after the `overdue_followup` entry):
```tsx
  { kind: "untriaged_message", label: "Untriaged messages" },
```
Run: `npm --prefix frontend install` (if needed) then `npm --prefix frontend run build` → succeeds.

- [ ] **Step 6: Full gate + commit**

Run: `bash scripts/ci/gate.sh` → GATE PASSED.
```bash
git add app/orchestration.py frontend/app/components/AttentionTab.tsx tests/test_attention_messages.py
git commit -m "feat(attention): surface untriaged inbound messages (captured SMS/email)"
```

---

### Task 3: `sms-analyser` capability

**Files:**
- Create: `skills/career-pack/skills/sms-analyser/SKILL.md`
- Modify: `app/capabilities.py` (entry)
- Modify: `tests/test_career_pack.py` (EXPECTED_SKILLS + count 12→13)
- Modify: `tests/test_capabilities.py` (count 12→13 + registry name set)
- Modify: `tests/test_capabilities_api.py` (by_name set + count 12→13)

- [ ] **Step 1: Update test expectations (these now fail)**

- `tests/test_career_pack.py`: add `"sms-analyser"` to `EXPECTED_SKILLS`; change `assert len(opts.skills) == 12` → `== 13`.
- `tests/test_capabilities.py`: change `assert len(caps.SKILL_NAMES) == 12` → `== 13`; add `"sms-analyser"` to the hardcoded capability-name set in `test_registry_has_the_expected_capabilities` (if present).
- `tests/test_capabilities_api.py`: add `"sms-analyser"` to the `set(by_name) == { … }` literal; change `assert len(names) == 12` → `== 13`.

- [ ] **Step 2: Run to verify failure**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_career_pack.py tests/test_capabilities.py tests/test_capabilities_api.py -q`
Expected: FAIL.

- [ ] **Step 3: Create the skill**

Create `skills/career-pack/skills/sms-analyser/SKILL.md`:
```markdown
---
name: sms-analyser
description: Use when the user pastes or forwards a text message (SMS) about an opportunity — log it as a communication plus any follow-up, never inventing details.
---

# SMS Analyser

Analyse ONE pasted text message (SMS) that relates to the given Opportunity, then
record what it means. You log facts about a real message — never invent a name,
date, or commitment that is not in the text.

## What to extract

Read the Input (the raw text) and the Opportunity block. Determine:
- **direction**: `inbound` if the user received it, `outbound` if they sent it
  (default `inbound`).
- **intent**: scheduling, a request, a confirmation, a rejection, or an update.
- **sender / number**: if shown, for the thread.
- **occurred_at**: a timestamp if shown, ISO 8601; omit if unknown.
- **asks / dates**: any time, date, or action requested — quote verbatim.

## Anti-fabrication rules (non-negotiable)

- Use ONLY facts present in the text. Never infer a follow-up date the message
  does not give.
- The `body` you store is the text itself (or a faithful summary if long).

## Steps

1. Read the Opportunity block (note its `id`) and the Input text.
2. Call `mcp__app__record_communication` to log the message (contract below).
3. If the text requires the user to do something (reply, confirm a time, send
   info), call `mcp__app__record_action` for that next step. If nothing is
   required, do not invent an action — say so in your reply.
4. Reply with a 1–2 line summary: the intent, what you logged, and any date the
   user must act on.

## Write-back contract

- `mcp__app__record_communication` — required `direction` (`inbound`/`outbound`)
  and `channel` (use `sms`); pass `opportunity_id` (the Opportunity `id`),
  `subject` (e.g. "SMS from <sender>"), `body` (the text), `occurred_at` (ISO
  8601, if known), `thread_key` (the sender number, if known), and
  `follow_up_due_at` (ISO 8601) ONLY when the text states/clearly implies a
  reply-by time.
- `mcp__app__record_action` — only when a next step is needed: `title`
  (imperative), `opportunity_id`, `kind` (`followup`/`outreach`/`prep`/`decision`),
  `detail` (include any time/date verbatim), and `due_at` (ISO 8601) only if a
  time is given.
```

- [ ] **Step 4: Add the capability entry**

In `app/capabilities.py`, after the `email-analyser` entry, add:
```python
    Capability(
        name="sms-analyser",
        skill="sms-analyser",
        label="Analyse text",
        description="Paste a text message about an opportunity; log it and capture follow-ups.",
        requires_opportunity=True,
        requires_input=True,
        include_profile=False,
        plugin=CAREER_PLUGIN,
    ),
```

- [ ] **Step 5: Run the tests + full gate**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_career_pack.py tests/test_capabilities.py tests/test_capabilities_api.py -q` → PASS
Then `bash scripts/ci/gate.sh` → GATE PASSED.

- [ ] **Step 6: Commit**

```bash
git add skills/career-pack/skills/sms-analyser/SKILL.md app/capabilities.py tests/test_career_pack.py tests/test_capabilities.py tests/test_capabilities_api.py
git commit -m "feat(career): sms-analyser capability (text -> communication + follow-up)"
```
