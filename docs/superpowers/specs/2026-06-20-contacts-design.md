# Design: Contacts

**Date:** 2026-06-20
**Status:** Approved design — ready for implementation plan
**Builds on:** the `Contact` model (name/role/organization/link/notes + opp/company
FKs), the application-tracking/comms-log slices (pattern), and the Detail tab.

## 1. Purpose

Track the people behind an opportunity — recruiters, hiring managers, referrers.
The `Contact` model exists but has no service/tool/API/UI. This adds the full
surface, with a Contacts section in the Detail tab that supports both agent-added
contacts and quick manual entry (you find a recruiter on LinkedIn and jot them
down).

## 2. Scope

Backend: `add_contact`/`list_contacts` service, a `record_contact` agent tool, a
`/api/contacts` router (GET + POST) + detail include. Frontend: a `Contact` type
+ fetchers and a Contacts section in `OpportunityDetailTab` with an inline add
form.

**Out of scope:** edit/delete contacts; a standalone Contacts tab (Detail is the
per-opportunity home); contact↔company auto-linking. Follows existing patterns
(`add_action`/`record_application`, `actions.py`, `OpportunityDetailTab`).

## 3. Service — `app/services.py`

Mirror `add_action`, with create-or-update-by-id (like `record_application`):

```python
def add_contact(
    session: Session,
    *,
    name: str,
    opportunity_id: str | None = None,
    role: str | None = None,
    organization: str | None = None,
    company_id: str | None = None,
    link: str | None = None,
    notes: str = "",
    contact_id: int | None = None,
) -> Contact: ...
```

- `contact_id is None` → create; else load that row and set its columns from the
  args (create-fallback if not found). When `opportunity_id` is set and the
  opportunity exists, bump its `last_activity_at`.
- `Contact` has `created_at` but no `updated_at` — do not set a non-existent field.

```python
def list_contacts(session: Session, opportunity_id: str | None = None) -> list[Contact]: ...
```
Ordered `created_at` desc; filtered by `opportunity_id` when provided.

## 4. Agent write-back tool — `app/agent/tools.py`

New `@tool("record_contact", ...)`, args: `name` (required), `role`,
`organization`, `link`, `notes`, `opportunity_id`, `company_id`, `contact_id`
(int → update). Calls `services.add_contact(...)`, returns `_ok(...)`. Registered
in `ALL_TOOLS`.

## 5. API — `app/routers/contacts.py` (new) + detail include

Mirror `actions.py` (which has GET + POST):
- `GET /api/contacts?opportunity_id=` → `list[Contact]`.
- `POST /api/contacts` with a `ContactCreate` body (`name` required;
  `opportunity_id`, `role`, `organization`, `link`, `notes` optional) →
  `services.add_contact(...)` → `Contact`. (This backs the UI inline add.)
- Register the router in `app/main.py`.
- Add `"contacts": services.list_contacts(session, opportunity_id=opp_id)` to the
  `get_opportunity` detail dict.

## 6. Frontend — `frontend/lib/api.ts`

```typescript
export type Contact = {
  id: number;
  opportunity_id: string | null;
  name: string;
  role: string | null;
  organization: string | null;
  company_id: string | null;
  link: string | null;
  notes: string;
  created_at: string;
};

export async function fetchContacts(oppId?: string): Promise<Contact[]> { ... }  // GET /api/contacts[?opportunity_id=]
export async function createContact(body: {
  name: string; opportunity_id?: string | null; role?: string | null;
  organization?: string | null; link?: string | null; notes?: string;
}): Promise<Contact> { ... }  // POST /api/contacts
```
- `OpportunityDetail` gains `contacts: Contact[]`.

## 7. Frontend — `OpportunityDetailTab`

Add a **Contacts** section (e.g. after Applications), using the existing
`Section`/`Badge` helpers:
- The list: per row — `name`, `role` (badge or muted text), a `link` as an
  external anchor when present, and `notes`.
- An **inline add form** (a small row inside the section): `name` `<input>`
  (required) + `role` `<input>` + `link` `<input>` + an **Add** button (disabled
  until name is non-empty). On submit: `createContact({ name, role: role || null,
  link: link || null, opportunity_id: opportunityId })` → clear the fields →
  `load()` (the tab's existing `useCallback`).

## 8. Testing

Backend test-first (deterministic temp SQLite; `Contact` already wiped in
`_clear_db`):
1. **Service** (`tests/test_contact_service.py`): create with defaults;
   update-by-id; `list_contacts` filters by opportunity; bumps
   `last_activity_at` when linked.
2. **Tool** (`tests/test_contact_tool.py`): the tool creates a row + returns
   `_ok`.
3. **API** (`tests/test_contact_api.py`): `GET` lists + filters; `POST` creates
   (returns the row; requires `name`); opportunity detail includes `contacts`.

Frontend verified via `npm --prefix frontend run build`.

## 9. Notes

- `POST /api/contacts` is the first read-API router to also expose a create
  endpoint for the UI (comms/applications were agent-write-only); it mirrors
  `actions.py`, which already pairs GET + POST.
- `Contact.id` is an int autoincrement PK (logs/children convention), so the
  TS type uses `number` and `contact_id` updates are numeric.
