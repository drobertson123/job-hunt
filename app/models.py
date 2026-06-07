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
corpus_documents, corpus_chunks, saved_queries.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
