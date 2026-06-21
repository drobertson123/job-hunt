# Forwarding Android SMS into Opportunity Hunter

Android lets a forwarder app read incoming texts and POST them to a URL. Because
the app is reachable over Tailscale, your phone can hit the webhook directly.

## 1. The endpoint

```
POST http://<tailscale-ip-or-name>:8000/api/communications/sms
Content-Type: application/json

{ "from": "{{sender}}", "body": "{{message}}" }
```

- `from` — the sender's number (becomes the message's `thread_key`, so texts
  from one number group together).
- `body` — the text. `received_at` (ISO 8601) and `opportunity_id` are optional.
- On success it stores an **inbound `sms` Communication** and returns it.
- Captured texts are **unlinked** at first and appear under **Attention →
  Untriaged messages**. Open the opportunity and run the **Analyse text**
  capability (paste the message) to link it and capture any follow-up.

## 2. Optional shared secret (recommended)

By default the webhook is open (it trusts the Tailscale network, like the rest of
the app). To require a secret, start the server with:

```bash
SMS_WEBHOOK_TOKEN=your-long-random-string python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then have the forwarder include it, either as a header `X-SMS-Token:
your-long-random-string` or as a query param `?token=your-long-random-string`.
A wrong/missing token returns `401`.

## 3. Forwarder app setup

Any "SMS → webhook" forwarder works. Examples:

**SMS Forwarder (URL/webhook) apps** — add an HTTP rule:
- URL: `http://<tailscale-ip>:8000/api/communications/sms`
- Method: `POST`, Content-Type: `application/json`
- Body template: `{"from":"%from%","body":"%text%"}` (placeholder syntax varies
  by app — use whatever tokens the app exposes for sender and message text).
- (Optional) Header `X-SMS-Token: <your secret>`.

**MacroDroid** — Trigger: *SMS Received* → Action: *HTTP Request (POST)* to the
URL with the JSON body above, substituting the `sms_sender` / `sms_message`
magic-text variables.

**Tasker** — Profile: *Event → Phone → Received Text* → Task: *HTTP Request*
(POST, JSON body using `%SMSRF` sender and `%SMSRB` body variables).

## 4. Test it

From any machine on the tailnet:

```bash
curl -X POST http://<tailscale-ip>:8000/api/communications/sms \
  -H 'Content-Type: application/json' \
  -d '{"from":"+15551234567","body":"Hi, are you free Tue for a quick call?"}'
```

It should return the created communication, and the message appears under
**Attention → Untriaged messages**.

## Note on iPhone

iOS gives apps no way to read incoming texts automatically. On iPhone, use the
**Analyse text** capability and paste/forward the message manually, or build an
iOS Share-sheet Shortcut that POSTs the selected text to the same endpoint.
