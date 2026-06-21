# Relationship Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five SQLModel entities (Company, JobSource, Application, Communication, Briefing) plus FK columns on `opportunities`/`contacts`, with migration — data layer only.

**Architecture:** Append new models to `app/models.py` following existing conventions; new tables are auto-created by `SQLModel.metadata.create_all`; new columns on existing tables are added idempotently via the existing `_ensure_column` helper in `app/db.py:init_db`. No services, API, agent tools, or UI.

**Tech Stack:** Python 3.12, SQLModel/SQLAlchemy, SQLite, pytest.

## Global Constraints

- Python 3.12; SQLModel `table=True` classes in `app/models.py`.
- Top-level entities use `id: str = Field(default_factory=_uuid, primary_key=True)`; logs/children use `id: int | None = Field(default=None, primary_key=True)`. Helpers `_uuid` and `_utcnow` already exist in `app/models.py`.
- JSON columns use `Field(default_factory=..., sa_column=Column(JSON))` (`JSON`, `Column` already imported).
- All tables carry `created_at`/`updated_at` (or at least `created_at` for logs) via `Field(default_factory=_utcnow)`.
- Keep existing string columns (`Opportunity.organization`, `Opportunity.source`, `Contact.organization`) untouched — new FKs are additive.
- Table names: `companies, job_sources, applications, communications, briefings`.
- Tests are deterministic (temp/in-memory SQLite via existing `tests/conftest.py`); no external API calls.
- Run the full suite with `.venv/bin/python -m pytest -q` (worktree shares the primary checkout's `.venv`; the gate uses `python -m pytest`).
- Task order is FK-safe: every referenced table (`companies`, `job_sources`, `opportunities`, `contacts`, `runs`) exists before a model references it. Do not reorder.

---

### Task 1: Company model

**Files:**
- Modify: `app/models.py` (append new section at end)
- Test: `tests/test_relationship_models.py` (create)

**Interfaces:**
- Produces: `CompanySize(str, Enum)` with members `startup, smb, mid, large, enterprise, unknown`; `Company` table (`companies`) with `id: str`, `name: str`, `domain: str|None`, `size: CompanySize` (default `unknown`), plus `industry, hq_location, careers_url, linkedin_url, ats_vendor, summary` (str|None), `notes: str`, `details: dict`, `created_at/updated_at`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_relationship_models.py
from __future__ import annotations

from sqlmodel import Session

from app.db import engine
from app.models import Company, CompanySize


def test_company_roundtrip_and_default_size():
    with Session(engine) as s:
        c = Company(name="Acme Corp", domain="acme.com", ats_vendor="Greenhouse")
        s.add(c)
        s.commit()
        s.refresh(c)
        assert c.id is not None and len(c.id) == 32  # _uuid hex
        assert c.size == CompanySize.unknown
        assert c.domain == "acme.com" and c.details == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_relationship_models.py::test_company_roundtrip_and_default_size -v`
Expected: FAIL with `ImportError: cannot import name 'Company'`.

- [ ] **Step 3: Write minimal implementation**

Append to `app/models.py`:

```python
# --------------------------------------------------------------------------- #
# Relationship models: Company, JobSource, Application, Communication, Briefing.
# Normalize loose strings (organization/source) and capture applications,
# comms, and structured briefings. See
# docs/superpowers/specs/2026-06-20-relationship-models-design.md.
# --------------------------------------------------------------------------- #


class CompanySize(str, Enum):
    startup = "startup"
    smb = "smb"
    mid = "mid"
    large = "large"
    enterprise = "enterprise"
    unknown = "unknown"


class Company(SQLModel, table=True):
    __tablename__ = "companies"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str
    domain: str | None = Field(default=None, index=True)
    industry: str | None = None
    size: CompanySize = Field(default=CompanySize.unknown)
    hq_location: str | None = None
    careers_url: str | None = None
    linkedin_url: str | None = None
    ats_vendor: str | None = None  # Greenhouse | Lever | Workday | Ashby | ...
    summary: str | None = None
    notes: str = ""
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_relationship_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_relationship_models.py
git commit -m "feat(models): add Company entity"
```

---

### Task 2: JobSource model

**Files:**
- Modify: `app/models.py` (append after Company)
- Test: `tests/test_relationship_models.py`

**Interfaces:**
- Consumes: `contacts.id` (existing, int PK).
- Produces: `JobSourceKind(str, Enum)` = `job_board, company_site, referral, recruiter, social, aggregator, other`; `JobSource` table (`job_sources`) with `id: str`, `name: str`, `kind: JobSourceKind` (default `other`), `url/saved_query: str|None`, `last_checked_at: datetime|None`, `referrer_contact_id: int|None` (FK `contacts.id`), `notes`, `created_at/updated_at`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_relationship_models.py
from app.models import JobSource, JobSourceKind  # noqa: E402


def test_jobsource_roundtrip_and_default_kind():
    with Session(engine) as s:
        js = JobSource(name="LinkedIn", url="https://linkedin.com/jobs",
                       saved_query="staff ml engineer remote")
        s.add(js)
        s.commit()
        s.refresh(js)
        assert js.id is not None and js.kind == JobSourceKind.other
        assert js.saved_query == "staff ml engineer remote"
        assert js.last_checked_at is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_relationship_models.py::test_jobsource_roundtrip_and_default_kind -v`
Expected: FAIL with `ImportError: cannot import name 'JobSource'`.

- [ ] **Step 3: Write minimal implementation**

Append to `app/models.py`:

```python
class JobSourceKind(str, Enum):
    job_board = "job_board"
    company_site = "company_site"
    referral = "referral"
    recruiter = "recruiter"
    social = "social"
    aggregator = "aggregator"
    other = "other"


class JobSource(SQLModel, table=True):
    __tablename__ = "job_sources"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str
    kind: JobSourceKind = Field(default=JobSourceKind.other)
    url: str | None = None
    saved_query: str | None = None  # discovery-ready feed; not polled yet
    last_checked_at: datetime | None = None
    referrer_contact_id: int | None = Field(
        default=None, foreign_key="contacts.id", index=True
    )
    notes: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_relationship_models.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_relationship_models.py
git commit -m "feat(models): add JobSource entity"
```

---

### Task 3: Application model

**Files:**
- Modify: `app/models.py` (append after JobSource)
- Test: `tests/test_relationship_models.py`

**Interfaces:**
- Consumes: `opportunities.id` (existing, str PK), `companies.id` (Task 1).
- Produces: `ApplicationStatus(str, Enum)` = `draft, submitted, under_review, interviewing, offer, rejected, withdrawn`; `Application` table (`applications`) with `id: str`, `opportunity_id: str` (FK, **required**), `company_id: str|None` (FK), `status: ApplicationStatus` (default `draft`), `portal_url/external_id/login_hint: str|None`, `submitted_at: datetime|None`, `notes`, `details: dict`, `created_at/updated_at`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_relationship_models.py
from app.models import Application, ApplicationStatus, Opportunity, OpportunityType  # noqa: E402


def test_application_requires_opportunity_and_defaults_draft():
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Staff ML Engineer")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        app_row = Application(opportunity_id=opp.id, portal_url="https://boards.greenhouse.io/x")
        s.add(app_row)
        s.commit()
        s.refresh(app_row)
        assert app_row.id is not None
        assert app_row.opportunity_id == opp.id
        assert app_row.status == ApplicationStatus.draft
        assert app_row.details == {} and app_row.submitted_at is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_relationship_models.py::test_application_requires_opportunity_and_defaults_draft -v`
Expected: FAIL with `ImportError: cannot import name 'Application'`.

- [ ] **Step 3: Write minimal implementation**

Append to `app/models.py`:

```python
class ApplicationStatus(str, Enum):
    draft = "draft"
    submitted = "submitted"
    under_review = "under_review"
    interviewing = "interviewing"
    offer = "offer"
    rejected = "rejected"
    withdrawn = "withdrawn"


class Application(SQLModel, table=True):
    __tablename__ = "applications"

    id: str = Field(default_factory=_uuid, primary_key=True)
    opportunity_id: str = Field(foreign_key="opportunities.id", index=True)
    company_id: str | None = Field(
        default=None, foreign_key="companies.id", index=True
    )
    status: ApplicationStatus = Field(default=ApplicationStatus.draft, index=True)
    portal_url: str | None = None
    external_id: str | None = None  # their application ID
    submitted_at: datetime | None = None
    login_hint: str | None = None
    notes: str = ""
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_relationship_models.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_relationship_models.py
git commit -m "feat(models): add Application entity"
```

---

### Task 4: Communication model

**Files:**
- Modify: `app/models.py` (append after Application)
- Test: `tests/test_relationship_models.py`

**Interfaces:**
- Consumes: `opportunities.id`, `contacts.id`, `companies.id`.
- Produces: `CommDirection(str, Enum)` = `inbound, outbound`; `CommChannel(str, Enum)` = `email, sms, linkedin, phone, in_person, other`; `Communication` table (`communications`) with `id: int`, `opportunity_id: str|None`, `contact_id: int|None`, `company_id: str|None`, `direction: CommDirection` (required), `channel: CommChannel` (required), `subject/body: str`, `occurred_at: datetime` (indexed), `thread_key: str|None`, `follow_up_due_at: datetime|None`, `created_at`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_relationship_models.py
from app.models import CommChannel, CommDirection, Communication  # noqa: E402


def test_communication_log_roundtrip():
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role X")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        msg = Communication(
            opportunity_id=opp.id,
            direction=CommDirection.inbound,
            channel=CommChannel.sms,
            subject="Re: interview",
            body="Can you do Tuesday?",
        )
        s.add(msg)
        s.commit()
        s.refresh(msg)
        assert msg.id is not None
        assert msg.channel == CommChannel.sms and msg.direction == CommDirection.inbound
        assert msg.occurred_at is not None and msg.follow_up_due_at is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_relationship_models.py::test_communication_log_roundtrip -v`
Expected: FAIL with `ImportError: cannot import name 'Communication'`.

- [ ] **Step 3: Write minimal implementation**

Append to `app/models.py`:

```python
class CommDirection(str, Enum):
    inbound = "inbound"
    outbound = "outbound"


class CommChannel(str, Enum):
    email = "email"
    sms = "sms"
    linkedin = "linkedin"
    phone = "phone"
    in_person = "in_person"
    other = "other"


class Communication(SQLModel, table=True):
    __tablename__ = "communications"

    id: int | None = Field(default=None, primary_key=True)
    opportunity_id: str | None = Field(
        default=None, foreign_key="opportunities.id", index=True
    )
    contact_id: int | None = Field(
        default=None, foreign_key="contacts.id", index=True
    )
    company_id: str | None = Field(
        default=None, foreign_key="companies.id", index=True
    )
    direction: CommDirection
    channel: CommChannel
    subject: str = ""
    body: str = ""
    occurred_at: datetime = Field(default_factory=_utcnow, index=True)
    thread_key: str | None = Field(default=None, index=True)
    follow_up_due_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_relationship_models.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_relationship_models.py
git commit -m "feat(models): add Communication log"
```

---

### Task 5: Briefing model

**Files:**
- Modify: `app/models.py` (append after Communication)
- Test: `tests/test_relationship_models.py`

**Interfaces:**
- Consumes: `opportunities.id`, `companies.id`, `runs.id` (existing, str PK).
- Produces: `BriefingFactKey(str, Enum)` = `salary_range, location, remote_policy, tech_stack, team, seniority, interview_process, company_health, why_fit, concerns, other`; `Briefing` table (`briefings`) with `id: int`, `opportunity_id: str|None`, `company_id: str|None`, `summary: str`, `facts: list[dict]` (entries `{key, question, answer, confidence, source}`), `source_hash: str|None`, `generated_run_id: str|None` (FK `runs.id`), `refreshed_at/created_at`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_relationship_models.py
from app.models import Briefing, BriefingFactKey  # noqa: E402


def test_briefing_facts_roundtrip():
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role Y")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        b = Briefing(
            opportunity_id=opp.id,
            summary="Strong fit; remote-first.",
            facts=[
                {"key": BriefingFactKey.salary_range.value, "question": "Salary range?",
                 "answer": "$180-220k", "confidence": 0.7, "source": "levels.fyi"},
                {"key": BriefingFactKey.other.value, "question": "Visa sponsorship?",
                 "answer": "Yes", "confidence": None, "source": None},
            ],
        )
        s.add(b)
        s.commit()
        s.refresh(b)
        assert b.id is not None and len(b.facts) == 2
        assert b.facts[0]["key"] == "salary_range"
        assert b.company_id is None and b.source_hash is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_relationship_models.py::test_briefing_facts_roundtrip -v`
Expected: FAIL with `ImportError: cannot import name 'Briefing'`.

- [ ] **Step 3: Write minimal implementation**

Append to `app/models.py`:

```python
class BriefingFactKey(str, Enum):
    """Fixed 'expected questions' a briefing should aim to answer; `other`
    covers freeform extras. Presence enforcement is a service concern."""

    salary_range = "salary_range"
    location = "location"
    remote_policy = "remote_policy"
    tech_stack = "tech_stack"
    team = "team"
    seniority = "seniority"
    interview_process = "interview_process"
    company_health = "company_health"
    why_fit = "why_fit"
    concerns = "concerns"
    other = "other"


class Briefing(SQLModel, table=True):
    __tablename__ = "briefings"

    id: int | None = Field(default=None, primary_key=True)
    opportunity_id: str | None = Field(
        default=None, foreign_key="opportunities.id", index=True
    )
    company_id: str | None = Field(
        default=None, foreign_key="companies.id", index=True
    )
    summary: str = ""
    # Each fact: {key: BriefingFactKey value, question, answer,
    #            confidence: float|None, source: str|None}
    facts: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    source_hash: str | None = None  # staleness marker (cf. GroundingReport)
    generated_run_id: str | None = Field(
        default=None, foreign_key="runs.id", index=True
    )
    refreshed_at: datetime = Field(default_factory=_utcnow)
    created_at: datetime = Field(default_factory=_utcnow)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_relationship_models.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_relationship_models.py
git commit -m "feat(models): add Briefing with fixed fact keys"
```

---

### Task 6: FK columns on Opportunity/Contact + migration + test wipe

**Files:**
- Modify: `app/models.py` (`Opportunity` class — add 2 fields; `Contact` class — add 1 field)
- Modify: `app/db.py` (`init_db` — add 3 `_ensure_column` calls)
- Modify: `tests/conftest.py` (`_clear_db` — register new models in the wipe)
- Test: `tests/test_relationship_models.py`

**Interfaces:**
- Consumes: `companies.id` (Task 1), `job_sources.id` (Task 2).
- Produces: `Opportunity.company_id: str|None` (FK `companies.id`), `Opportunity.source_id: str|None` (FK `job_sources.id`), `Contact.company_id: str|None` (FK `companies.id`); `init_db()` adds these columns on pre-existing DBs.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_relationship_models.py
import sqlalchemy as sa  # noqa: E402

from app.db import _ensure_column  # noqa: E402
from app.models import Contact  # noqa: E402


def test_opportunity_and_contact_fk_columns_roundtrip():
    with Session(engine) as s:
        co = Company(name="Globex")
        src = JobSource(name="Referral", kind=JobSourceKind.referral)
        s.add(co)
        s.add(src)
        s.commit()
        s.refresh(co)
        s.refresh(src)
        opp = Opportunity(type=OpportunityType.job, title="Role Z",
                          company_id=co.id, source_id=src.id)
        contact = Contact(name="Jane Recruiter", company_id=co.id)
        s.add(opp)
        s.add(contact)
        s.commit()
        s.refresh(opp)
        s.refresh(contact)
        assert opp.company_id == co.id and opp.source_id == src.id
        assert contact.company_id == co.id


def test_ensure_column_is_idempotent(tmp_path):
    # File-backed sqlite: `sqlite://` is in-memory and gives a *fresh* DB per
    # connection, so _ensure_column's own connection wouldn't see the table.
    eng = sa.create_engine(f"sqlite:///{tmp_path}/t.db")
    with eng.connect() as c:
        c.exec_driver_sql("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        c.commit()
    _ensure_column(eng, "t", "company_id", "VARCHAR")
    _ensure_column(eng, "t", "company_id", "VARCHAR")  # second call must no-op
    with eng.connect() as c:
        cols = [r[1] for r in c.exec_driver_sql("PRAGMA table_info(t)")]
    assert cols.count("company_id") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_relationship_models.py::test_opportunity_and_contact_fk_columns_roundtrip tests/test_relationship_models.py::test_ensure_column_is_idempotent -v`
Expected: FAIL (`TypeError: 'company_id' is an invalid keyword argument for Opportunity` / unknown attribute).

- [ ] **Step 3: Add fields to Opportunity and Contact**

In `app/models.py`, inside `class Opportunity`, after the `dedupe_key` line add:

```python
    company_id: str | None = Field(
        default=None, foreign_key="companies.id", index=True
    )
    source_id: str | None = Field(
        default=None, foreign_key="job_sources.id", index=True
    )
```

In `app/models.py`, inside `class Contact`, after the `organization` line add:

```python
    company_id: str | None = Field(
        default=None, foreign_key="companies.id", index=True
    )
```

- [ ] **Step 4: Add migration calls to init_db**

In `app/db.py`, in `init_db()`, after the existing `_ensure_column(engine, "artifacts", ...)` line add:

```python
    # Relationship models: pre-existing DBs lack these FK columns.
    _ensure_column(engine, "opportunities", "company_id", "VARCHAR")
    _ensure_column(engine, "opportunities", "source_id", "VARCHAR")
    _ensure_column(engine, "contacts", "company_id", "VARCHAR")
```

- [ ] **Step 5: Register new models in the per-test wipe**

In `tests/conftest.py`, inside `_clear_db`, extend the import and the delete tuple so the new tables are cleared between tests. Add `Application, Briefing, Communication, Company, JobSource` to the `from app.models import (...)` block, and add them to the front of the delete tuple (FK enforcement is off in SQLite, so order is non-critical, but list children first):

```python
        for model in (
            Briefing, Communication, Application,
            GroundingReport, Artifact, Action, Decision, Contact,
            Opportunity, JobSource, Company, Chunk, Document, Profile,
        ):
            s.exec(delete(model))
```

- [ ] **Step 6: Run the new tests, then the full suite**

Run: `.venv/bin/python -m pytest tests/test_relationship_models.py -v`
Expected: PASS (7 tests).

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all prior tests + 7 new; 0 failures).

- [ ] **Step 7: Commit**

```bash
git add app/models.py app/db.py tests/conftest.py tests/test_relationship_models.py
git commit -m "feat(models): wire Company/JobSource FKs onto Opportunity+Contact with migration"
```

---

## Final verification

- [ ] Run the local gate: `scripts/ci/gate.sh` → GATE PASSED.
- [ ] Confirm `git log --oneline` shows 6 focused commits on `feature/relationship-models`.

## Self-Review (completed by plan author)

- **Spec coverage:** Company (T1), JobSource (T2), Application (T3), Communication (T4), Briefing + fixed `BriefingFactKey` + freeform `other` (T5), FK columns on opportunities/contacts + `_ensure_column` migration + idempotency (T6). All 5 spec acceptance criteria covered: table creation (conftest `init_db` exercises all; T1–T5 round-trips), enum defaults (T1 `unknown`, T2 `other`, T3 `draft`), JSON round-trip (T3 details, T5 facts), pre-existing-DB migration + idempotency (T6), required `opportunity_id` on Application / optional links on Communication+Briefing (T3/T4/T5).
- **Placeholder scan:** none — every step has concrete code/commands.
- **Type consistency:** str-uuid FKs (`company_id`, `source_id`, `opportunity_id`, `generated_run_id`) reference str-PK tables; int FKs (`contact_id`, `referrer_contact_id`) reference int-PK `contacts`. Enum member names match between model defs and test imports.
