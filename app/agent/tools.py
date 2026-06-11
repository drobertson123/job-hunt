"""In-process MCP tools — the artifact->schema write-back seam.

These run in-process (same Python process as FastAPI) via the SDK's in-process
MCP server, so they have direct DB access and go through the SAME service layer
as the HTTP API. The current run is carried via a contextvar set by the runner
so a tool call can attribute its writes (e.g. artifact provenance) to its run.

Authored skills (Phase 2) will be written to call these tools, which is how a
free-form chat turn turns into structured rows in the system of record.
"""

from __future__ import annotations

from datetime import datetime
from contextvars import ContextVar
from enum import Enum
from typing import Any, TypeVar

from claude_agent_sdk import create_sdk_mcp_server, tool
from sqlmodel import Session

from app import services
from app.db import engine
from app.models import (
    ActionKind,
    ArtifactFormat,
    ArtifactKind,
    DecisionKind,
    Note,
    OpportunityType,
    PipelineStage,
)

# Set by the runner before each query() so tools can attribute their writes.
current_run_id: ContextVar[str | None] = ContextVar("current_run_id", default=None)

MCP_SERVER_NAME = "app"


def _name(tool_name: str) -> str:
    return f"mcp__{MCP_SERVER_NAME}__{tool_name}"


SAVE_NOTE_TOOL = _name("save_note")

E = TypeVar("E", bound=Enum)


def _enum(cls: type[E], value: Any, default: E) -> E:
    try:
        return cls(value)
    except (ValueError, KeyError, TypeError):
        return default


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _ok(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


# --------------------------------------------------------------------------- #


@tool(
    "save_note",
    "Save a short note to the user's workspace (appears in their canvas).",
    {"title": str, "body": str},
)
async def save_note(args: dict[str, Any]) -> dict[str, Any]:
    title = (args.get("title") or "").strip() or "Untitled note"
    with Session(engine) as s:
        note = Note(title=title, body=args.get("body") or "", run_id=current_run_id.get())
        s.add(note)
        s.commit()
        s.refresh(note)
        return _ok(f"Saved note #{note.id}: {title!r}.")


@tool(
    "save_opportunity",
    "Create or update a job or business opportunity in the user's pipeline. "
    "Pass a stable dedupe_key (e.g. the URL or company+title) to update idempotently.",
    {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["job", "business"]},
            "title": {"type": "string", "description": "Role title or opportunity name"},
            "organization": {"type": "string"},
            "url": {"type": "string"},
            "location": {"type": "string"},
            "summary": {"type": "string"},
            "source": {"type": "string", "description": "paste | url | discovery | manual"},
            "dedupe_key": {"type": "string"},
            "details": {"type": "object", "description": "Type-specific fields"},
        },
        "required": ["type", "title"],
    },
)
async def save_opportunity(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        opp = services.upsert_opportunity(
            s,
            type=_enum(OpportunityType, args.get("type"), OpportunityType.job),
            title=args["title"],
            dedupe_key=args.get("dedupe_key"),
            organization=args.get("organization"),
            url=args.get("url"),
            location=args.get("location"),
            summary=args.get("summary"),
            source=args.get("source") or "agent",
            details=args.get("details") or {},
        )
        return _ok(f"Saved opportunity {opp.id} ({opp.type.value}): {opp.title!r}.")


@tool(
    "update_pipeline_status",
    "Move an opportunity to a new pipeline stage (logs the change).",
    {
        "type": "object",
        "properties": {
            "opportunity_id": {"type": "string"},
            "stage": {
                "type": "string",
                "enum": ["new", "qualifying", "analyzing", "active", "in_dialogue", "won", "lost"],
            },
            "rationale": {"type": "string"},
        },
        "required": ["opportunity_id", "stage"],
    },
)
async def update_pipeline_status(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        opp = services.get_opportunity(s, args["opportunity_id"])
        if opp is None:
            return {**_ok(f"No opportunity {args['opportunity_id']}."), "is_error": True}
        stage = _enum(PipelineStage, args.get("stage"), opp.stage)
        services.set_stage(s, opp, stage, rationale=args.get("rationale") or "")
        return _ok(f"Moved {opp.title!r} to {stage.value}.")


@tool(
    "record_action",
    "Record a next action / task, optionally linked to an opportunity and due date.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "opportunity_id": {"type": "string"},
            "kind": {
                "type": "string",
                "enum": ["followup", "apply", "research", "prep", "outreach", "decision", "other"],
            },
            "detail": {"type": "string"},
            "due_at": {"type": "string", "description": "ISO 8601 datetime"},
        },
        "required": ["title"],
    },
)
async def record_action(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        action = services.add_action(
            s,
            title=args["title"],
            opportunity_id=args.get("opportunity_id"),
            kind=_enum(ActionKind, args.get("kind"), ActionKind.other),
            detail=args.get("detail") or "",
            due_at=_parse_dt(args.get("due_at")),
        )
        return _ok(f"Recorded action #{action.id}: {action.title!r}.")


@tool(
    "save_artifact",
    "Save a generated deliverable (CV, cover letter, research brief, etc.) as a "
    "versioned artifact linked to an opportunity. It appears in the canvas.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "body": {"type": "string", "description": "Markdown content"},
            "opportunity_id": {"type": "string"},
            "kind": {
                "type": "string",
                "enum": [
                    "note", "cv", "cover_letter", "research_brief", "fit_analysis",
                    "pitch", "proposal", "outreach", "other",
                ],
            },
            "provenance": {"type": "string", "description": "Which skill produced it"},
        },
        "required": ["title", "body"],
    },
)
async def save_artifact(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        artifact = services.add_artifact(
            s,
            title=args["title"],
            body=args.get("body") or "",
            opportunity_id=args.get("opportunity_id"),
            kind=_enum(ArtifactKind, args.get("kind"), ArtifactKind.other),
            format=ArtifactFormat.markdown,
            provenance=args.get("provenance"),
            run_id=current_run_id.get(),
        )
        return _ok(f"Saved artifact #{artifact.id} ({artifact.kind.value}) v{artifact.version}.")


@tool(
    "record_decision",
    "Record a choice or feedback (e.g. why the user passed on an opportunity).",
    {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "opportunity_id": {"type": "string"},
            "kind": {"type": "string", "enum": ["stage_change", "choice", "feedback", "note"]},
            "rationale": {"type": "string"},
        },
        "required": ["summary"],
    },
)
async def record_decision(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        d = services.record_decision(
            s,
            summary=args["summary"],
            opportunity_id=args.get("opportunity_id"),
            kind=_enum(DecisionKind, args.get("kind"), DecisionKind.note),
            rationale=args.get("rationale") or "",
        )
        return _ok(f"Recorded decision #{d.id}.")


ALL_TOOLS = [
    save_note,
    save_opportunity,
    update_pipeline_status,
    record_action,
    save_artifact,
    record_decision,
]

# Tool names the agent is allowed to call (mcp__app__*).
ALL_TOOL_NAMES = [_name(t.name) for t in ALL_TOOLS]


def build_app_mcp_server():
    """Create the in-process MCP server exposing the app's write-back tools."""
    return create_sdk_mcp_server(name=MCP_SERVER_NAME, tools=ALL_TOOLS)
