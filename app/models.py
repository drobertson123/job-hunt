"""Phase 0 data model.

Deliberately minimal — just what the vertical slice needs:
  * Setting  — key/value for UI-entered config (API keys, model overrides).
  * Run      — one agent invocation (the durable source of truth for streaming).
  * Event    — append-only log of what the agent emitted during a Run
               (tokens, tool calls, status). Enables re-attach/cancel after a
               dropped phone connection.
  * Note     — what the `save_note` MCP tool writes; the write-back-seam probe
               and the first thing the canvas renders.

Later phases add: opportunities, actions, artifacts, decisions, contacts,
saved_queries.

Phase 2 adds: corpus_documents, corpus_chunks, profile, grounding_reports
(+ Artifact.review_status).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    # Naive UTC: SQLite stores datetimes without tz, so keeping them naive and
    # consistent avoids offset-suffix string-comparison bugs in time queries.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _uuid() -> str:
    return uuid.uuid4().hex


class Setting(SQLModel, table=True):
    __tablename__ = "settings"

    key: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(default_factory=_utcnow)


class RunStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"


class Run(SQLModel, table=True):
    __tablename__ = "runs"

    id: str = Field(default_factory=_uuid, primary_key=True)
    prompt: str
    model: str | None = None
    status: RunStatus = Field(default=RunStatus.pending)
    cwd: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class EventType(str, Enum):
    token = "token"  # streamed assistant text delta
    tool_use = "tool_use"  # agent invoked a tool
    tool_result = "tool_result"  # result of a tool call
    status = "status"  # run lifecycle (running/completed/...)
    error = "error"
    result = "result"  # final result payload


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="runs.id", index=True)
    seq: int = Field(index=True)  # monotonic per run; clients resume from last seq
    type: EventType
    # Free-form payload: text for tokens, JSON string for tool calls/results.
    content: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class Note(SQLModel, table=True):
    __tablename__ = "notes"

    id: int | None = Field(default=None, primary_key=True)
    title: str
    body: str = ""
    run_id: str | None = Field(default=None, foreign_key="runs.id", index=True)
    created_at: datetime = Field(default_factory=_utcnow)


# --------------------------------------------------------------------------- #
# Phase 1: the normalized system-of-record.
# Core fields are shared across job/business; type-specific data lives in the
# `details` JSON column so the two domains coexist without sparse columns.
# --------------------------------------------------------------------------- #


class OpportunityType(str, Enum):
    job = "job"
    business = "business"


class PipelineStage(str, Enum):
    """A generic funnel that fits both tracks; type nuance lives in actions."""

    new = "new"
    qualifying = "qualifying"
    analyzing = "analyzing"
    active = "active"  # applied / pursuing / submitted
    in_dialogue = "in_dialogue"  # interviewing / negotiating
    won = "won"
    lost = "lost"


# Order for board columns + advance(); transitions themselves are unrestricted
# (personal tool) but every change is logged as a Decision.
STAGE_ORDER: list[PipelineStage] = [
    PipelineStage.new,
    PipelineStage.qualifying,
    PipelineStage.analyzing,
    PipelineStage.active,
    PipelineStage.in_dialogue,
    PipelineStage.won,
    PipelineStage.lost,
]


class Opportunity(SQLModel, table=True):
    __tablename__ = "opportunities"

    id: str = Field(default_factory=_uuid, primary_key=True)
    type: OpportunityType
    title: str
    organization: str | None = None
    source: str | None = None  # paste | url | discovery | manual
    url: str | None = Field(default=None, index=True)
    location: str | None = None
    stage: PipelineStage = Field(default=PipelineStage.new, index=True)
    fit_score: float | None = None  # 0-100
    summary: str | None = None
    # Type-specific: job -> {salary, seniority, employment_type, skills, ...};
    # business -> {opportunity_kind (rfp|grant|startup|fractional|partnership),
    # value_estimate, deadline, ...}.
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    dedupe_key: str | None = Field(default=None, index=True)  # idempotent upsert
    company_id: str | None = Field(default=None, foreign_key="companies.id", index=True)
    source_id: str | None = Field(default=None, foreign_key="job_sources.id", index=True)
    archived: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    last_activity_at: datetime = Field(default_factory=_utcnow)


class ActionStatus(str, Enum):
    open = "open"
    done = "done"
    snoozed = "snoozed"
    canceled = "canceled"


class ActionKind(str, Enum):
    followup = "followup"
    apply = "apply"
    research = "research"
    prep = "prep"
    outreach = "outreach"
    decision = "decision"
    other = "other"


class Action(SQLModel, table=True):
    __tablename__ = "actions"

    id: int | None = Field(default=None, primary_key=True)
    opportunity_id: str | None = Field(
        default=None, foreign_key="opportunities.id", index=True
    )
    title: str
    detail: str = ""
    kind: ActionKind = ActionKind.other
    status: ActionStatus = Field(default=ActionStatus.open, index=True)
    due_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None


class ArtifactKind(str, Enum):
    note = "note"
    cv = "cv"
    cover_letter = "cover_letter"
    research_brief = "research_brief"
    fit_analysis = "fit_analysis"
    pitch = "pitch"
    proposal = "proposal"
    outreach = "outreach"
    other = "other"


class ArtifactFormat(str, Enum):
    markdown = "markdown"
    docx = "docx"
    pdf = "pdf"


class ReviewStatus(str, Enum):
    """Review-before-send gate: grounding check -> needs_review -> human approval."""

    draft = "draft"
    needs_review = "needs_review"
    approved = "approved"


class Artifact(SQLModel, table=True):
    __tablename__ = "artifacts"

    id: int | None = Field(default=None, primary_key=True)
    opportunity_id: str | None = Field(
        default=None, foreign_key="opportunities.id", index=True
    )
    kind: ArtifactKind = ArtifactKind.other
    title: str
    format: ArtifactFormat = ArtifactFormat.markdown
    body: str = ""  # markdown content (or a summary if file-backed)
    file_path: str | None = None
    provenance: str | None = None  # which skill/source produced it
    version: int = 1
    review_status: ReviewStatus = Field(default=ReviewStatus.draft, index=True)
    run_id: str | None = Field(default=None, foreign_key="runs.id", index=True)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class DecisionKind(str, Enum):
    stage_change = "stage_change"
    choice = "choice"
    feedback = "feedback"
    note = "note"


class Decision(SQLModel, table=True):
    __tablename__ = "decisions"

    id: int | None = Field(default=None, primary_key=True)
    opportunity_id: str | None = Field(
        default=None, foreign_key="opportunities.id", index=True
    )
    kind: DecisionKind = DecisionKind.note
    summary: str
    rationale: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class Contact(SQLModel, table=True):
    __tablename__ = "contacts"

    id: int | None = Field(default=None, primary_key=True)
    opportunity_id: str | None = Field(
        default=None, foreign_key="opportunities.id", index=True
    )
    name: str
    role: str | None = None
    organization: str | None = None
    company_id: str | None = Field(default=None, foreign_key="companies.id", index=True)
    link: str | None = None
    notes: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


# --------------------------------------------------------------------------- #
# Phase 2: Corpus / RAG substrate + Profile synthesis.
# --------------------------------------------------------------------------- #


class DocumentSource(str, Enum):
    upload = "upload"
    paste = "paste"


class DocumentMediaType(str, Enum):
    pdf = "pdf"
    docx = "docx"
    txt = "txt"
    md = "md"


class Document(SQLModel, table=True):
    __tablename__ = "corpus_documents"

    id: int | None = Field(default=None, primary_key=True)
    title: str
    source_kind: DocumentSource = DocumentSource.upload
    media_type: DocumentMediaType = DocumentMediaType.txt
    raw_text: str = ""
    content_hash: str = Field(index=True)  # sha256 of raw_text → dedup/idempotency
    char_count: int = 0
    created_at: datetime = Field(default_factory=_utcnow)


class Chunk(SQLModel, table=True):
    __tablename__ = "corpus_chunks"

    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="corpus_documents.id", index=True)
    seq: int = 0
    text: str = ""
    embedding: bytes = b""  # numpy float32 .tobytes()
    embedding_model: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class Profile(SQLModel, table=True):
    __tablename__ = "profile"

    id: int | None = Field(default=None, primary_key=True)
    headline: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    experience: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    achievements: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    target_titles: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    locations: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    pinned_skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    source_doc_count: int = 0
    synthesized_at: datetime = Field(default_factory=_utcnow)


# --------------------------------------------------------------------------- #
# Phase 2 slice C: grounding reports (anti-fabrication verifier output).
# --------------------------------------------------------------------------- #


class GroundingReport(SQLModel, table=True):
    """One current grounding report per artifact (replaced on re-check).

    `body_hash` is sha256 of the artifact body that was checked; a mismatch vs
    the current body means the report is stale. Annotated text is derived from
    body + findings offsets, never stored.
    """

    __tablename__ = "grounding_reports"

    id: int | None = Field(default=None, primary_key=True)
    artifact_id: int = Field(foreign_key="artifacts.id", index=True, unique=True)
    body_hash: str
    threshold: float
    embedding_model: str = ""
    # Per sentence: {text, start, end, score, chunk_id|None,
    #               document_title|None, supported}
    findings: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    checked_count: int = 0
    unsupported_count: int = 0
    created_at: datetime = Field(default_factory=_utcnow)


# --------------------------------------------------------------------------- #
# Relationship models: Company, JobSource, Application, Communication, Briefing.
# Normalize loose strings (organization/source) and capture applications, comms,
# and structured briefings. See
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
    auto_search: bool = False  # opt in to the daily scheduler
    last_checked_at: datetime | None = None
    referrer_contact_id: int | None = Field(
        default=None, foreign_key="contacts.id", index=True
    )
    notes: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


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
    company_id: str | None = Field(default=None, foreign_key="companies.id", index=True)
    status: ApplicationStatus = Field(default=ApplicationStatus.draft, index=True)
    portal_url: str | None = None
    external_id: str | None = None  # their application ID
    submitted_at: datetime | None = None
    login_hint: str | None = None
    notes: str = ""
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class CommDirection(str, Enum):
    inbound = "inbound"
    outbound = "outbound"


class CommChannel(str, Enum):
    email = "email"
    sms = "sms"
    linkedin = "linkedin"
    whatsapp = "whatsapp"
    phone = "phone"
    in_person = "in_person"
    other = "other"


class Communication(SQLModel, table=True):
    __tablename__ = "communications"

    id: int | None = Field(default=None, primary_key=True)
    opportunity_id: str | None = Field(
        default=None, foreign_key="opportunities.id", index=True
    )
    contact_id: int | None = Field(default=None, foreign_key="contacts.id", index=True)
    company_id: str | None = Field(default=None, foreign_key="companies.id", index=True)
    direction: CommDirection
    channel: CommChannel
    subject: str = ""
    body: str = ""
    occurred_at: datetime = Field(default_factory=_utcnow, index=True)
    thread_key: str | None = Field(default=None, index=True)
    follow_up_due_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow)


class InterviewKind(str, Enum):
    phone = "phone"
    video = "video"
    onsite = "onsite"
    technical = "technical"
    behavioral = "behavioral"
    final = "final"
    other = "other"


class InterviewEvent(SQLModel, table=True):
    __tablename__ = "interview_events"

    id: int | None = Field(default=None, primary_key=True)
    opportunity_id: str | None = Field(
        default=None, foreign_key="opportunities.id", index=True
    )
    title: str
    kind: InterviewKind = InterviewKind.other
    starts_at: datetime = Field(index=True)
    ends_at: datetime | None = None
    location: str = ""
    notes: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


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
    company_id: str | None = Field(default=None, foreign_key="companies.id", index=True)
    summary: str = ""
    # Each fact: {key: BriefingFactKey value, question, answer,
    #            confidence: float|None, source: str|None}
    facts: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    source_hash: str | None = None  # staleness marker (cf. GroundingReport)
    generated_run_id: str | None = Field(default=None, foreign_key="runs.id", index=True)
    refreshed_at: datetime = Field(default_factory=_utcnow)
    created_at: datetime = Field(default_factory=_utcnow)
