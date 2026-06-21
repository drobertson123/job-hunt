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

from app import briefing_service, corpus_service, services
from app.db import engine
from app.models import (
    ActionKind,
    ApplicationStatus,
    ArtifactFormat,
    ArtifactKind,
    CommChannel,
    CommDirection,
    CompanySize,
    ContentBlockKind,
    DecisionKind,
    InterviewKind,
    JobSourceKind,
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
    "record_application",
    "Record or update a job application to an opportunity (ATS/portal + status).",
    {
        "type": "object",
        "properties": {
            "opportunity_id": {"type": "string"},
            "status": {
                "type": "string",
                "enum": ["draft", "submitted", "under_review", "interviewing",
                         "offer", "rejected", "withdrawn"],
            },
            "company_id": {"type": "string"},
            "portal_url": {"type": "string"},
            "external_id": {"type": "string"},
            "submitted_at": {"type": "string", "description": "ISO 8601 datetime"},
            "login_hint": {"type": "string"},
            "notes": {"type": "string"},
            "application_id": {
                "type": "string",
                "description": "set to update an existing application",
            },
        },
        "required": ["opportunity_id"],
    },
)
async def record_application(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        app_row = services.record_application(
            s,
            opportunity_id=args["opportunity_id"],
            status=_enum(ApplicationStatus, args.get("status"), ApplicationStatus.draft),
            company_id=args.get("company_id"),
            portal_url=args.get("portal_url"),
            external_id=args.get("external_id"),
            submitted_at=_parse_dt(args.get("submitted_at")),
            login_hint=args.get("login_hint"),
            notes=args.get("notes") or "",
            application_id=args.get("application_id"),
        )
        return _ok(
            f"Recorded application {app_row.id} "
            f"({app_row.status.value}) for opportunity {app_row.opportunity_id}."
        )


@tool(
    "record_company",
    "Create or enrich a company (industry, size, ATS vendor, careers URL, ...). "
    "Only provided fields are updated; omit a field to leave it unchanged.",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "domain": {"type": "string"},
            "industry": {"type": "string"},
            "size": {
                "type": "string",
                "enum": ["startup", "smb", "mid", "large", "enterprise", "unknown"],
            },
            "hq_location": {"type": "string"},
            "careers_url": {"type": "string"},
            "linkedin_url": {"type": "string"},
            "ats_vendor": {"type": "string"},
            "summary": {"type": "string"},
            "notes": {"type": "string"},
            "company_id": {"type": "string", "description": "set to enrich an existing company"},
            "link_opportunity_id": {
                "type": "string",
                "description": "set to link this opportunity to the company",
            },
        },
        "required": ["name"],
    },
)
async def record_company(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        size = _enum(CompanySize, args["size"], CompanySize.unknown) if args.get("size") else None
        c = services.upsert_company(
            s,
            name=args["name"],
            domain=args.get("domain"),
            industry=args.get("industry"),
            size=size,
            hq_location=args.get("hq_location"),
            careers_url=args.get("careers_url"),
            linkedin_url=args.get("linkedin_url"),
            ats_vendor=args.get("ats_vendor"),
            summary=args.get("summary"),
            notes=args.get("notes"),
            company_id=args.get("company_id"),
            link_opportunity_id=args.get("link_opportunity_id"),
        )
        return _ok(f"Recorded company {c.id}: {c.name}.")


@tool(
    "record_job_source",
    "Record or enrich where an opportunity came from (job board, referral, "
    "recruiter, saved search), optionally linking it to an opportunity.",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "kind": {
                "type": "string",
                "enum": ["job_board", "company_site", "referral", "recruiter",
                         "social", "aggregator", "other"],
            },
            "url": {"type": "string"},
            "saved_query": {"type": "string"},
            "notes": {"type": "string"},
            "referrer_contact_id": {"type": "integer"},
            "job_source_id": {"type": "string", "description": "set to enrich an existing source"},
            "link_opportunity_id": {
                "type": "string",
                "description": "set to attribute this opportunity to the source",
            },
        },
        "required": ["name"],
    },
)
async def record_job_source(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        kind = _enum(JobSourceKind, args["kind"], JobSourceKind.other) if args.get("kind") else None
        js = services.upsert_job_source(
            s,
            name=args["name"],
            kind=kind,
            url=args.get("url"),
            saved_query=args.get("saved_query"),
            notes=args.get("notes"),
            referrer_contact_id=args.get("referrer_contact_id"),
            job_source_id=args.get("job_source_id"),
            link_opportunity_id=args.get("link_opportunity_id"),
        )
        return _ok(f"Recorded job source {js.id}: {js.name}.")


@tool(
    "record_communication",
    "Log a communication (email/SMS/LinkedIn/phone/in-person) for an opportunity, "
    "with an optional follow-up due date that surfaces in the attention queue.",
    {
        "type": "object",
        "properties": {
            "direction": {"type": "string", "enum": ["inbound", "outbound"]},
            "channel": {
                "type": "string",
                "enum": ["email", "sms", "linkedin", "phone", "in_person", "other"],
            },
            "opportunity_id": {"type": "string"},
            "contact_id": {"type": "integer"},
            "company_id": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "occurred_at": {"type": "string", "description": "ISO 8601 datetime"},
            "thread_key": {"type": "string"},
            "follow_up_due_at": {"type": "string", "description": "ISO 8601 datetime"},
            "communication_id": {
                "type": "integer",
                "description": "set to update an existing communication",
            },
        },
        "required": ["direction", "channel"],
    },
)
async def record_communication(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        c = services.record_communication(
            s,
            direction=_enum(CommDirection, args.get("direction"), CommDirection.outbound),
            channel=_enum(CommChannel, args.get("channel"), CommChannel.other),
            opportunity_id=args.get("opportunity_id"),
            contact_id=args.get("contact_id"),
            company_id=args.get("company_id"),
            subject=args.get("subject") or "",
            body=args.get("body") or "",
            occurred_at=_parse_dt(args.get("occurred_at")),
            thread_key=args.get("thread_key"),
            follow_up_due_at=_parse_dt(args.get("follow_up_due_at")),
            communication_id=args.get("communication_id"),
        )
        return _ok(
            f"Logged {c.direction.value} {c.channel.value} communication {c.id}."
        )


@tool(
    "schedule_interview",
    "Schedule an interview event for an opportunity (date/time, type, location/link).",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "starts_at": {"type": "string", "description": "ISO 8601 datetime"},
            "opportunity_id": {"type": "string"},
            "kind": {
                "type": "string",
                "enum": ["phone", "video", "onsite", "technical", "behavioral", "final", "other"],
            },
            "ends_at": {"type": "string", "description": "ISO 8601 datetime"},
            "location": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["title", "starts_at"],
    },
)
async def schedule_interview(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        starts = _parse_dt(args.get("starts_at"))
        if starts is None:
            return _ok("Could not schedule interview: starts_at (ISO 8601) is required.")
        ev = services.add_interview(
            s,
            title=args.get("title") or "Interview",
            starts_at=starts,
            opportunity_id=args.get("opportunity_id"),
            kind=_enum(InterviewKind, args.get("kind"), InterviewKind.other),
            ends_at=_parse_dt(args.get("ends_at")),
            location=args.get("location") or "",
            notes=args.get("notes") or "",
        )
        return _ok(f"Scheduled interview #{ev.id}: {ev.title!r} at {ev.starts_at.isoformat()}.")


@tool(
    "synthesize_briefing",
    "Synthesize a structured briefing (salary, remote, tech stack, why-fit, "
    "concerns, ...) for an opportunity, grounded in its data and the user's corpus.",
    {
        "type": "object",
        "properties": {"opportunity_id": {"type": "string"}},
        "required": ["opportunity_id"],
    },
)
async def synthesize_briefing(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        briefing = await briefing_service.synthesize_briefing(
            s,
            opportunity_id=args["opportunity_id"],
            generated_run_id=current_run_id.get(),
        )
        return _ok(
            f"Synthesized briefing for opportunity {briefing.opportunity_id} "
            f"({len(briefing.facts)} facts)."
        )


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
    "record_contact",
    "Record a person tied to an opportunity (recruiter, hiring manager, referrer).",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "opportunity_id": {"type": "string"},
            "role": {"type": "string"},
            "organization": {"type": "string"},
            "company_id": {"type": "string"},
            "link": {"type": "string"},
            "notes": {"type": "string"},
            "contact_id": {"type": "integer", "description": "set to update an existing contact"},
        },
        "required": ["name"],
    },
)
async def record_contact(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        c = services.add_contact(
            s,
            name=args["name"],
            opportunity_id=args.get("opportunity_id"),
            role=args.get("role"),
            organization=args.get("organization"),
            company_id=args.get("company_id"),
            link=args.get("link"),
            notes=args.get("notes") or "",
            contact_id=args.get("contact_id"),
        )
        return _ok(f"Recorded contact {c.id}: {c.name}.")


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


@tool(
    "save_content_block",
    "Save a reusable career content block (headline, summary, or achievement bullet) to the library.",
    {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "kind": {"type": "string", "enum": ["headline", "summary", "bullet", "other"]},
            "audience": {"type": "string", "description": "positioning tag, e.g. technical / leadership"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["text"],
    },
)
async def save_content_block(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        block = services.add_content_block(
            s,
            kind=_enum(ContentBlockKind, args.get("kind"), ContentBlockKind.bullet),
            text=args.get("text") or "",
            audience=args.get("audience") or "",
            tags=args.get("tags") or [],
            provenance="career-pack:content-library",
        )
        return _ok(f"Saved content block #{block.id} ({block.kind.value}).")


def _corpus_embedder(session: Session):
    """Indirection point: tests monkeypatch this to inject a fake embedder."""
    return corpus_service.default_embedder(session)


@tool(
    "search_corpus",
    "Search the user's career corpus (their uploaded CV, notes, and documents) "
    "for passages relevant to a query. Returns ranked excerpts with their source.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "k": {"type": "integer", "description": "max results (default 8)"},
        },
        "required": ["query"],
    },
)
async def search_corpus(args: dict[str, Any]) -> dict[str, Any]:
    query = (args.get("query") or "").strip()
    if not query:
        return _ok("No query provided.")
    k = max(1, int(args.get("k") or 8))
    with Session(engine) as s:
        try:
            embedder = _corpus_embedder(s)
        except RuntimeError as exc:
            # e.g. no OpenAI key configured — hand the agent a message it can
            # reason about and relay, rather than crashing the tool handler.
            return {**_ok(str(exc)), "is_error": True}
        hits = corpus_service.search(s, query, embedder=embedder, k=k)
    if not hits:
        return _ok("No matching passages in the corpus.")
    lines = [f"[{h.document_title}] (score {h.score:.3f})\n{h.chunk_text}" for h in hits]
    return _ok("\n\n---\n\n".join(lines))


ALL_TOOLS = [
    save_note,
    save_opportunity,
    update_pipeline_status,
    record_action,
    record_application,
    record_company,
    record_job_source,
    record_communication,
    schedule_interview,
    record_contact,
    synthesize_briefing,
    save_artifact,
    record_decision,
    search_corpus,
    save_content_block,
]

# Tool names the agent is allowed to call (mcp__app__*).
ALL_TOOL_NAMES = [_name(t.name) for t in ALL_TOOLS]


def build_app_mcp_server():
    """Create the in-process MCP server exposing the app's write-back tools."""
    return create_sdk_mcp_server(name=MCP_SERVER_NAME, tools=ALL_TOOLS)
