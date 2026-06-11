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

Phase 2 adds: corpus_documents, corpus_chunks, profile.
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
    source_doc_count: int = 0
    synthesized_at: datetime = Field(default_factory=_utcnow)
