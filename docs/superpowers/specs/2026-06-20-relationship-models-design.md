# Design: Relationship Models (Company, JobSource, Application, Communication, Briefing)

**Date:** 2026-06-20
**Status:** Approved design — ready for implementation plan
**Scope:** Data models + migration ONLY (no services, API, agent tools, or UI)

## 1. Purpose

Add five entities that turn loose strings and absent records into first-class,
queryable data for the job hunt:

- **Company** — normalize the `organization` string into a reusable entity.
- **JobSource** — capture where each lead came from (attribution), with
  discovery-ready saved feeds (no automation yet).
- **Application** — a first-class record of *applying* to an opportunity through
  an ATS/portal, distinct from the opportunity itself.
- **Communication** — a log of inbound/outbound messages (email/SMS/LinkedIn/
  phone), feeding follow-ups.
- **Briefing** — a structured quick-reference for an opportunity/company:
  answers to expected questions (salary range, location, …) plus freeform extras.

These follow existing `app/models.py` conventions: top-level entities use `_uuid`
string PKs; logs/children use autoincrement int PKs; type-specific extras go in a
`details` JSON column; all tables carry `_utcnow` timestamps.

## 2. Out of scope (separate specs)

Services, API routes, agent write-back tools, and UI for these entities;
discovery automation/polling; interview coaching; backfilling `company_id`/
`source_id` from existing `organization`/`source` strings. Existing string
columns (`Opportunity.organization`, `Opportunity.source`, `Contact.organization`)
are **kept as denormalized display labels**; the new FKs are source-of-truth when
set.

## 3. New models

### 3.1 Company — `companies` (str uuid PK)
| field | type | notes |
|-------|------|-------|
| id | str | `_uuid` PK |
| name | str | required |
| domain | str \| None | indexed; soft dedup key |
| industry | str \| None | |
| size | `CompanySize` | enum, default `unknown` |
| hq_location | str \| None | |
| careers_url | str \| None | |
| linkedin_url | str \| None | |
| ats_vendor | str \| None | e.g. Greenhouse/Lever/Workday/Ashby |
| summary | str \| None | |
| notes | str | default "" |
| details | dict (JSON) | default {} |
| created_at / updated_at | datetime | `_utcnow` |

`CompanySize` enum: `startup, smb, mid, large, enterprise, unknown`.

### 3.2 JobSource — `job_sources` (str uuid PK)
| field | type | notes |
|-------|------|-------|
| id | str | `_uuid` PK |
| name | str | required |
| kind | `JobSourceKind` | enum, default `other` |
| url | str \| None | |
| saved_query | str \| None | discovery-ready feed; not polled |
| last_checked_at | datetime \| None | |
| referrer_contact_id | int \| None | FK `contacts.id`, for referrals |
| notes | str | default "" |
| created_at / updated_at | datetime | `_utcnow` |

`JobSourceKind` enum: `job_board, company_site, referral, recruiter, social, aggregator, other`.

### 3.3 Application — `applications` (str uuid PK)
| field | type | notes |
|-------|------|-------|
| id | str | `_uuid` PK |
| opportunity_id | str | FK `opportunities.id`, **required**, indexed |
| company_id | str \| None | FK `companies.id`, convenience |
| status | `ApplicationStatus` | enum, default `draft`, indexed |
| portal_url | str \| None | |
| external_id | str \| None | their application ID |
| submitted_at | datetime \| None | |
| login_hint | str \| None | |
| notes | str | default "" |
| details | dict (JSON) | default {} |
| created_at / updated_at | datetime | `_utcnow` |

`ApplicationStatus` enum: `draft, submitted, under_review, interviewing, offer, rejected, withdrawn`.
One opportunity → many applications (usually one; allows re-apply). This status is
portal/ATS state, distinct from the internal `PipelineStage`.

### 3.4 Communication — `communications` (int PK, append-only log)
| field | type | notes |
|-------|------|-------|
| id | int | autoincrement PK |
| opportunity_id | str \| None | FK `opportunities.id`, indexed |
| contact_id | int \| None | FK `contacts.id`, indexed |
| company_id | str \| None | FK `companies.id` |
| direction | `CommDirection` | enum |
| channel | `CommChannel` | enum |
| subject | str | default "" |
| body | str | default "" |
| occurred_at | datetime | indexed; `_utcnow` default |
| thread_key | str \| None | indexed; groups a thread |
| follow_up_due_at | datetime \| None | indexed; feeds attention queue |
| created_at | datetime | `_utcnow` |

`CommDirection` enum: `inbound, outbound`. `CommChannel` enum: `email, sms, linkedin, phone, in_person, other`.

### 3.5 Briefing — `briefings` (int PK)
| field | type | notes |
|-------|------|-------|
| id | int | autoincrement PK |
| opportunity_id | str \| None | FK `opportunities.id`, indexed |
| company_id | str \| None | FK `companies.id`, indexed |
| summary | str | default "" |
| facts | list (JSON) | see below |
| source_hash | str \| None | staleness marker (mirrors `GroundingReport.body_hash`) |
| generated_run_id | str \| None | FK `runs.id`, provenance |
| refreshed_at | datetime | `_utcnow` |
| created_at | datetime | `_utcnow` |

At least one of `opportunity_id` / `company_id` is set (service-enforced later;
model leaves both nullable). `facts` is a list of entries:
`{key: BriefingFactKey, question: str, answer: str, confidence: float|None, source: str|None}`.

`BriefingFactKey` enum (the "fixed expected questions" + `other` for freeform
extras): `salary_range, location, remote_policy, tech_stack, team, seniority,
interview_process, company_health, why_fit, concerns, other`.
The fixed set is *expected* (a synthesizer should aim to fill them); enforcement
of presence is a service concern, out of scope here.

## 4. Changes to existing tables

Add nullable FK columns (source-of-truth when set; string labels retained):

- `opportunities`: `company_id` (str → `companies.id`), `source_id` (str → `job_sources.id`)
- `contacts`: `company_id` (str → `companies.id`)

## 5. Migration

Reuse the existing primitive in `app/db.py`:

- New tables (`companies, job_sources, applications, communications, briefings`)
  are created automatically by `SQLModel.metadata.create_all(engine)`.
- New columns on existing tables are added idempotently via `_ensure_column`
  calls in `init_db()` (same pattern as `artifacts.review_status`):
  - `_ensure_column(engine, "opportunities", "company_id", "VARCHAR")`
  - `_ensure_column(engine, "opportunities", "source_id", "VARCHAR")`
  - `_ensure_column(engine, "contacts", "company_id", "VARCHAR")`

SQLite does not enforce FKs by default and `ALTER TABLE ADD COLUMN` can't add a
FK constraint to an existing table; the SQLModel `foreign_key=` on these columns
documents intent and drives ORM relationships, while the added columns are plain
`VARCHAR`. This matches how `review_status` was introduced.

## 6. Testing (TDD per constitution)

Even though scope is models + migration, the work is test-first. Acceptance:

1. All five tables are created by `init_db()` on a fresh DB.
2. Each enum has the specified members and model defaults (`CompanySize.unknown`,
   `ApplicationStatus.draft`, `JobSourceKind.other`).
3. Round-trip: insert + query one row of each model, including JSON `details`/
   `facts` and a `BriefingFactKey`-tagged fact entry.
4. Migration on a **pre-existing** DB (tables created without the new columns)
   adds `opportunities.company_id`, `opportunities.source_id`,
   `contacts.company_id`; `_ensure_column` is idempotent on a second `init_db()`.
5. An `Application` requires `opportunity_id`; a `Communication` and `Briefing`
   can exist with only an opportunity link.

Tests are deterministic (in-memory/temp SQLite); no external API calls.

## 7. Risks / notes

- `details`/`facts` JSON columns follow the existing `sa_column=Column(JSON)`
  pattern used by `Opportunity.details` and `Profile`/`GroundingReport`.
- Keeping string labels avoids breaking existing rows, queries, and the live
  data already loaded.
- `models.py` is growing; group the new models under a clear
  `# Relationship models` section header to keep it navigable (no split now —
  YAGNI; revisit if it gets unwieldy).
