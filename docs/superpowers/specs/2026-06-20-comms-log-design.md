# Design: Communications Log + Attention Follow-ups

**Date:** 2026-06-20
**Status:** Approved design — ready for implementation plan
**Builds on:** the `Communication` model (added 2026-06-20), the application-tracking
slice (pattern), the Opportunity Detail tab, and the Attention tab.

## 1. Purpose

Let the agent log communications (email/SMS/LinkedIn/phone/…) per opportunity,
surface them in the opportunity Detail tab, and — when a communication carries a
`follow_up_due_at` that has passed — surface it in the Attention tab so
follow-ups don't get missed. First use of the `Communication` model; makes the
Attention tab actionable.

## 2. Scope

A vertical slice mirroring application tracking, plus an Attention extension:
service + agent write-back tool + read API + Detail-tab section, and a new
`overdue_followup` item kind in `needs_attention` surfaced by the Attention tab.

**Out of scope:** a standalone Comms canvas tab (Detail is the per-opportunity
home — avoids an 8th tab); a "resolved" flag (clear a follow-up by updating the
comm's `follow_up_due_at` to null); contact/company-scoped comm views; editing
comms from the UI (writes go through the agent). Existing patterns are followed.

## 3. Service — `app/services.py`

Mirror `record_application` (keyword-only, commits, bumps the linked opportunity).

```python
def record_communication(
    session: Session,
    *,
    direction: CommDirection,
    channel: CommChannel,
    opportunity_id: str | None = None,
    contact_id: int | None = None,
    company_id: str | None = None,
    subject: str = "",
    body: str = "",
    occurred_at: datetime | None = None,
    thread_key: str | None = None,
    follow_up_due_at: datetime | None = None,
    communication_id: int | None = None,
) -> Communication: ...
```

Behavior:
- `communication_id is None` → create; else load that row and set columns from
  args (create-fallback if id not found). `occurred_at` defaults to `_utcnow()`
  on create when not provided (the model default already does this — only set it
  when the arg is non-None). `updated_at` — the model has no `updated_at`; do not
  invent one.
- When `opportunity_id` is set and the opportunity exists, bump its
  `last_activity_at` (same as `add_action`/`record_application`).

```python
def list_communications(
    session: Session, opportunity_id: str | None = None
) -> list[Communication]: ...
```
Ordered `occurred_at` desc; filtered by `opportunity_id` when provided.

## 4. Agent write-back tool — `app/agent/tools.py`

New `@tool("record_communication", ...)`, args:
- `direction` (required, enum: inbound|outbound), `channel` (required, enum:
  email|sms|linkedin|phone|in_person|other),
- optional: `opportunity_id`, `contact_id` (int), `company_id`, `subject`,
  `body`, `occurred_at` (ISO), `thread_key`, `follow_up_due_at` (ISO),
  `communication_id` (int → update).
Parse enums via `_enum(...)`, dates via `_parse_dt(...)`, call
`services.record_communication(...)`, return `_ok(...)`. Register in `ALL_TOOLS`.

## 5. API — `app/routers/communications.py` (new) + detail include

- `GET /api/communications?opportunity_id=` → `list[Communication]`. Register the
  router in `app/main.py`.
- Add `"communications": services.list_communications(session, opportunity_id=opp_id)`
  to the `get_opportunity` detail dict.
- No POST — writes go through the agent tool.

## 6. Attention extension — `app/orchestration.py`

In `needs_attention`, after the untriaged block, query Communications whose
`follow_up_due_at` is non-null and `< now`:

```python
overdue_followups = session.exec(
    select(Communication).where(
        Communication.follow_up_due_at.is_not(None),
        Communication.follow_up_due_at < now,
    )
).all()
```

For each, append an item:
```python
{
  "kind": "overdue_followup",
  "severity": "high",
  "opportunity_id": c.opportunity_id,
  "communication_id": c.id,
  "title": c.subject or f"{c.channel.value} {c.direction.value}",
  "due_at": c.follow_up_due_at.isoformat(),
  "reason": "Follow-up overdue",
}
```

Add `"overdue_followups": len(overdue_followups)` to the `counts` dict.
`total` is `len(items)` (already), so it includes these automatically.

**Contract change:** `/api/attention` `counts` gains an `overdue_followups`
key (additive). The existing `test_needs_attention_surfaces_the_right_items`
only asserts specific keys and does not add comms, so it stays green; a new test
covers the overdue-followup case.

## 7. Frontend — `frontend/lib/api.ts`

```typescript
export type Communication = {
  id: number;
  opportunity_id: string | null;
  contact_id: number | null;
  company_id: string | null;
  direction: string;
  channel: string;
  subject: string;
  body: string;
  occurred_at: string;
  thread_key: string | null;
  follow_up_due_at: string | null;
  created_at: string;
};

export async function fetchCommunications(oppId?: string): Promise<Communication[]> { ... } // GET /api/communications[?opportunity_id=]
```
- `OpportunityDetail` gains `communications: Communication[]`.
- `Attention.counts` gains `overdue_followups: number`.

## 8. Frontend — components

- **`OpportunityDetailTab`**: add a **Communications** section (after
  Applications): per row — direction + channel badge, subject, occurred date,
  and a follow-up date when present (highlight if past-due). Reads
  `detail.communications`.
- **`AttentionTab`**: add an **Overdue follow-ups** group (`kind:
  "overdue_followup"`) to the `GROUPS` array (first, since severity high), and an
  "Overdue follow-ups" count badge from `counts.overdue_followups`. The existing
  loose `AttentionItem` type already covers the new item's fields
  (`opportunity_id`, `title`, `reason`, `due_at`).

## 9. Testing

Backend test-first (deterministic temp SQLite):
1. **Service** (`tests/test_communication_service.py`): create with defaults;
   update-by-id; `list_communications` filters by opportunity; bumps
   `last_activity_at` when linked.
2. **Tool** (`tests/test_communication_tool.py`): tool creates a row + returns
   `_ok`; bad enum falls back (direction/channel defaults — see note).
3. **API** (`tests/test_communication_api.py`): list endpoint + filter; detail
   includes `communications`.
4. **Orchestration** (extend `tests/test_domain.py`): a Communication with a past
   `follow_up_due_at` produces an `overdue_followup` item and increments
   `counts.overdue_followups`; one with a future/None follow-up does not.

Frontend verified via `npm --prefix frontend run build`. `communications` is
added to `tests/conftest.py` `_clear_db` (the table was already registered there
when the relationship models landed — confirm; add if missing).

## 10. Notes / decisions

- `direction`/`channel` are required on the model (no default). The tool requires
  them too; for the "bad enum" tool test, `_enum` falls back to a default — pick
  `CommDirection.outbound` / `CommChannel.other` as the tool's fallbacks so a
  malformed value still produces a row rather than erroring.
- No "resolved" concept: an overdue follow-up keeps surfacing until the comm's
  `follow_up_due_at` is cleared/updated (by the agent). Documented limitation.
- `Communication` has `created_at` but no `updated_at`; updates set columns
  in-place without touching a non-existent field.
