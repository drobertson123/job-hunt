# SMS Ingestion (Android) — Design

## Goal
Capture SMS from the user's Android phone into Opportunity Hunter: an inbound
webhook a phone-side forwarder app POSTs to, captured texts surfaced for triage,
and an `sms-analyser` capability to extract a text into a linked Communication +
follow-up. The `Communication` model already has `channel = sms`, so no schema
change is needed.

## Platform note
Android lets a forwarder app (Tasker / MacroDroid / "SMS Forwarder") read
incoming SMS and POST them to a URL. The app is reachable over Tailscale, so the
phone hits the webhook directly. (iOS has no API to auto-read texts — out of
scope; the `sms-analyser` capability still serves manual paste there.)

## 1. Webhook — `POST /api/communications/sms`
On the existing communications router. Records an **inbound** `sms` Communication
via the existing `record_communication` service (Constitution II — typed service
write).
- Body (Pydantic, `populate_by_name`): `from` (aliased to `sender`), `body`,
  optional `received_at` (ISO), optional `opportunity_id`.
- `thread_key = sender` so texts from one number group into a thread;
  `subject = "SMS from {sender}"`; `occurred_at = received_at or now`.
- **Optional shared-secret auth:** config `sms_webhook_token` (default `None`).
  When set, the request must carry it via `X-SMS-Token` header **or** `?token=`
  query (forwarder apps vary); mismatch → 401. Default-off matches the app's
  existing local-first / Tailscale-only no-auth posture, but the knob lets the
  user harden a write endpoint. Documented as recommended.

## 2. Surface captured texts — Attention queue
Captured SMS arrive **unlinked** (no `opportunity_id`). Add an
`untriaged_message` bucket to `needs_attention` (`app/orchestration.py`): inbound
Communications with `opportunity_id IS NULL` → one item each (`severity medium`,
channel, occurred_at, "not yet linked to an opportunity") plus a count. This
makes captured texts visible/actionable in the existing **Attention** tab instead
of piling up unseen. Benefits inbound email too.

## 3. `sms-analyser` capability
A career-pack skill mirroring `email-analyser`: `requires_opportunity=True`,
`requires_input=True`. Paste/forward a text → the agent logs an inbound `sms`
Communication (via `record_communication`) linked to the chosen opportunity, and
a follow-up `Action` if the text asks for one. Anti-fabrication: only what's in
the text. (Updates the capability registry + the static count tests 12→13.)

## 4. Android forwarder recipe
`docs/sms-forwarding-android.md`: configure a forwarder app to POST
`{"from": "<sender>", "body": "<message>"}` (+ optional token) to
`http://<tailscale-ip>:8000/api/communications/sms`.

## Out of scope
A full inbound-message inbox UI / auto-linking by sender→contact→opportunity
(future); iOS automatic capture (OS-restricted).

## Testing
- Webhook: POST creates an inbound sms Communication (thread_key=sender);
  token-gated path returns 401 on mismatch and 200 when correct / when unset.
- Attention: an unlinked inbound Communication appears as `untriaged_message`
  with a count; a linked one does not.
- Capability: `sms-analyser` registered; static count tests 12→13; skill has the
  required `## Write-back contract` + `mcp__app__` markers.
Gate green. No frontend change (Attention tab renders the new item kind generically).
