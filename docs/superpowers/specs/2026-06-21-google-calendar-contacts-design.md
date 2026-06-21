# Google Calendar + Contacts Sync — Design

## Goal
On the existing Google OAuth foundation, add **Calendar** (push interview events
to the user's Google Calendar; remove them on delete) and **Contacts** (import
Google contacts → app Contacts; push app contacts → Google). Built with an
injectable HTTP seam so tests never touch the network; live activation reuses the
single Google connection.

## Scope expansion (one consent covers all)
Add to `google_oauth.DEFAULT_SCOPES`:
`https://www.googleapis.com/auth/calendar.events` and
`https://www.googleapis.com/auth/contacts`. The user hasn't connected yet, so
their first consent grants Gmail + Calendar + Contacts together. (`prompt=consent`
already forces the grant.)

## HTTP seam
A single injectable `request(method, url, access_token, *, json=None, params=None)
-> dict` per service (default a thin `httpx.request` wrapper, `raise_for_status`,
returns `{}` on empty body). Tests pass a fake.

## Calendar — `app/gcal_service.py`
- `InterviewEvent.gcal_event_id: str | None` (new column + `_ensure_column`).
- `event_body(iv)` → Google event JSON: `summary=title`, `location`,
  `description=notes`, `start/end = {dateTime: <naive-iso>, timeZone: "UTC"}`
  (`end` defaults to `start+1h` when `ends_at` is None). Stored datetimes are
  naive-UTC (app convention) — documented.
- `push_interview(session, iv, *, access_token, request)` — POST a new event
  (store `gcal_event_id`) or PATCH the existing one.
- `delete_event(access_token, event_id, *, request)` — DELETE (idempotent; 404 ok).
- `sync_upcoming(session, *, access_token, request)` — push every upcoming
  InterviewEvent, returns `{pushed, updated}`.
- The interview DELETE endpoint also removes the Google event (best-effort) when
  connected and `gcal_event_id` is set.

## Contacts — `app/gcontacts_service.py`
- `Contact.google_resource_name: str | None` (dedup key) and `Contact.email:
  str | None` (new columns + migrations).
- `import_contacts(session, *, access_token, request)` — GET People
  `connections` (`personFields=names,emailAddresses,organizations`), upsert a
  Contact per connection keyed on `resourceName` (skip if already imported);
  returns `{imported, skipped}`.
- `push_contact(session, contact, *, access_token, request)` — create a Google
  contact (`people:createContact`) from the app Contact (name/email/org), store
  the returned `resourceName`; if already linked, PATCH
  (`updateContact`). Returns the resourceName.

## Endpoints — `app/routers/google.py`
- `POST /api/google/calendar/sync` → push upcoming interviews.
- `POST /api/google/contacts/import` → import Google contacts.
- `POST /api/google/contacts/{id}/push` → push one app contact.
(All call `go.get_access_token` first.)

## UI
- Interviews tab: a **Sync to Google Calendar** button (POST calendar/sync, show
  counts).
- Contacts (in OpportunityDetailTab) + Settings: an **Import Google contacts**
  button and a per-contact **Push to Google** affordance.
(Minimal; reuse token styling.)

## Service additions
- `services.add_contact` / contact create path gains optional `email`.
- Contact list/read returns the new fields.

## Testing
- `gcal_service`: `event_body` shape (summary/start/end +1h default/timeZone);
  `push_interview` POST-then-store-id, PATCH-when-linked (fake request records
  method+url+json); `sync_upcoming` counts; `delete_event` calls DELETE.
- `gcontacts_service`: `import_contacts` upserts + dedupes on resourceName;
  `push_contact` create-then-store / update-when-linked.
- Endpoints: each calls the service with a valid token (oauth + service stubbed),
  returns counts; interview DELETE removes the Google event when linked.
- Migrations additive/idempotent. Frontend `next build`.
Gate green. No live network in tests. Constitution II honored (contacts written
through the service layer; interviews already are).
