---
name: email-analyser
description: Use when the user pastes an email about an opportunity — extract its meaning and log it as a communication plus any follow-up, never inventing details.
---

# Email Analyser

Analyse ONE pasted email that relates to the given Opportunity, then record what
it means in the tracker. You log facts about a real message — never invent a
date, name, or commitment that is not in the email.

## What to extract

Read the Input (the raw email) and the Opportunity block. Determine:
- **direction**: `inbound` if the user received it, `outbound` if they sent it
  (default `inbound` — analysing a received email is the common case).
- **intent**: interview invite, scheduling, request for info/documents,
  rejection, offer, or general update.
- **subject**: the email's subject line (or a short one you derive if absent).
- **occurred_at**: the email's date/time if shown, as ISO 8601; omit if unknown.
- **key dates / asks**: any interview date/time, deadline, or action the user
  must take — quote them verbatim, do not normalise or guess.

## Anti-fabrication rules (non-negotiable)

- Use ONLY facts present in the email. If a date or detail is not stated, leave
  it out — never infer a follow-up date the email does not give.
- The `body` you store is a concise faithful summary plus any verbatim key lines
  (dates, names, requests). Do not embellish.

## Steps

1. Read the Opportunity block (note its `id`) and the Input email.
2. Call `mcp__app__record_communication` to log the message (contract below).
3. If the email requires the user to do something (reply, schedule, send
   documents, prepare, decide), call `mcp__app__record_action` for that next
   step. If it requires nothing (e.g. a plain rejection or FYI), do not invent
   an action — say so in your reply.
4. Reply with a 2–3 line summary: the intent, what you logged, and any date the
   user must act on.

## Write-back contract

- `mcp__app__record_communication` — required `direction` (`inbound`/`outbound`)
  and `channel` (use `email`); pass `opportunity_id` (the Opportunity `id`),
  `subject`, `body` (your faithful summary), `occurred_at` (ISO 8601, if known),
  `thread_key` (stable per email thread, e.g. the normalised subject), and
  `follow_up_due_at` (ISO 8601) ONLY when the email states or clearly implies a
  reply-by date.
- `mcp__app__record_action` — only when a next step is needed: `title`
  (imperative, e.g. "Reply to recruiter with availability"), `opportunity_id`,
  `kind` (`followup`/`prep`/`outreach`/`apply`/`decision`), `detail` (include any
  interview date/time verbatim from the email), and `due_at` (ISO 8601) only if a
  date is given.
