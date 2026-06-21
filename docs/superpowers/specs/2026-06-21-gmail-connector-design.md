# Google OAuth Foundation + Gmail Connector — Design

## Goal
Connect the user's Google account (OAuth2) and ingest job-related Gmail messages
into `Communication` rows. This is the **shared OAuth foundation** that Calendar
and Contacts (next slices) reuse. Built with injectable HTTP so it's unit-tested
deterministically; live activation needs the user's one-time Google Cloud setup.

## Trust / verification model
The app is local-first, single-user, Tailscale-only. Google client id/secret and
the OAuth tokens are stored in the existing `settings` key/value table (like the
OpenAI/Anthropic keys) — on the user's machine, never returned by the API. Token
refresh keeps access alive (no re-consent). Unit tests stub Google with injected
HTTP callables; a documented live path is the user connecting their account.

## OAuth flow (installed-app / loopback)
1. User creates a Google Cloud project, enables the Gmail API, and makes an
   OAuth **Desktop** client → `client_id` + `client_secret`, entered in Settings.
2. `GET /api/google/oauth/start` builds the consent URL (scopes
   `gmail.readonly` + `userinfo.email`, `access_type=offline`, `prompt=consent`,
   a random `state`) and 302-redirects the browser to Google.
3. Google redirects back to `GET /api/google/oauth/callback?code&state` (loopback
   `http://127.0.0.1:8000/...`). The app verifies `state`, exchanges the code for
   tokens, fetches the account email, stores the token blob, and shows a
   "Connected" page.
4. `google_oauth.get_access_token(session)` returns a valid access token,
   refreshing via the refresh token when within ~60s of expiry and re-persisting.

> **Loopback constraint (documented):** Google only allows `localhost`/`127.0.0.1`
> redirect URIs for Desktop clients, so the *connect* step is done from the
> machine running the server (or an SSH port-forward). Ongoing sync works over
> Tailscale once connected.

## Modules
- `app/google_oauth.py` (pure + injectable `poster`): `build_auth_url(...)`,
  `exchange_code(...)`, `refresh(...)`, `save_token/load_token`,
  `get_access_token(session, *, now, poster)`, `status(session)`.
- `app/gmail_service.py` (injectable `fetcher`): `sync(session, *, query,
  access_token, now, max_messages)` → lists message ids for `query`, fetches each,
  maps to a `Communication` (channel=email, direction inbound/outbound by sender
  vs. account email, subject/body/occurred_at from headers/internalDate,
  `thread_key=threadId`, `external_id=message id`), **dedupes on `external_id`**,
  returns `{fetched, created, skipped}`.
- `app/routers/google.py`: `GET /status`, `GET /oauth/start`, `GET /oauth/callback`,
  `POST /gmail/sync` (prefix `/api/google`).
- `settings_service`: keys `google_client_id`, `google_client_secret`,
  `google_oauth_token` (JSON), `google_oauth_state`; resolver helpers.

## Schema
`Communication.external_id: str | None` (the provider message id) +
`_ensure_column(engine, "communications", "external_id", "VARCHAR")`. Dedup query:
`select(Communication).where(Communication.external_id == msg_id)`.

## UI (minimal)
Settings gains two fields (Google client id/secret) + a **Connect Google** link
(opens `/api/google/oauth/start`) and a **Sync Gmail** button (POSTs the sync,
shows counts). Ingested mail then appears under **Attention → Untriaged messages**
and can be triaged with the existing `email-analyser` capability.

## Setup guide
`docs/google-setup.md`: the ~5-minute Google Cloud steps (project, enable Gmail
API, OAuth consent screen with the user as a test user, create Desktop client,
paste id/secret, click Connect).

## Out of scope (next slices)
Calendar two-way sync and Contacts two-way sync (reuse this OAuth foundation, add
their scopes). Sending mail. Full-thread rendering.

## Testing
- `build_auth_url`: contains client_id, redirect_uri, the scopes, state,
  `access_type=offline`.
- `exchange_code`/`refresh`: stubbed `poster` → token blob parsed; expiry computed
  from `expires_in` + injected `now`.
- `get_access_token`: returns stored token when fresh; refreshes + re-persists when
  expired (stubbed poster); raises a clear error when not connected.
- `gmail_service.sync`: stubbed `fetcher` returns 2 messages → 2 Communications
  created with correct fields; re-running creates 0 (dedup on external_id);
  direction inbound vs outbound by sender.
- Endpoints: `/status` reflects connected state; `/oauth/start` 302s to Google;
  `/oauth/callback` with a bad state → 400; `/gmail/sync` returns counts (oauth +
  gmail stubbed/monkeypatched).
Gate green. No live network in tests. Constitution II honored — Gmail writes go
through `record_communication`.
