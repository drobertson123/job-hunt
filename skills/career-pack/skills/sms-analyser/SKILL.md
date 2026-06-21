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
