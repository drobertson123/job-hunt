"""In-process MCP tools — the artifact->schema write-back seam (Phase 0 probe).

These run in-process (same Python process as FastAPI) via the SDK's in-process
MCP server, so they have direct DB access. The current run is carried via a
contextvar set by the runner before `query()` is invoked, so a tool call can
attribute its row to the run that triggered it.

Phase 0 exposes a single `save_note` tool to prove the seam: the agent decides
to call it, a structured row lands in SQLite, and the canvas renders it.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Annotated, Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from sqlmodel import Session

from app.db import engine
from app.models import Note

# Set by the runner before each query() so tools can attribute their writes.
current_run_id: ContextVar[str | None] = ContextVar("current_run_id", default=None)

MCP_SERVER_NAME = "app"
# Tool names the agent sees: mcp__<server>__<tool>
SAVE_NOTE_TOOL = f"mcp__{MCP_SERVER_NAME}__save_note"


@tool(
    "save_note",
    "Save a short note to the user's workspace. Call this to record a takeaway, "
    "summary, or any text the user should keep. The note appears in their canvas.",
    {
        "title": Annotated[str, "Short title for the note"],
        "body": Annotated[str, "The note content (markdown allowed)"],
    },
)
async def save_note(args: dict[str, Any]) -> dict[str, Any]:
    title = (args.get("title") or "").strip() or "Untitled note"
    body = args.get("body") or ""
    with Session(engine) as session:
        note = Note(title=title, body=body, run_id=current_run_id.get())
        session.add(note)
        session.commit()
        session.refresh(note)
        note_id = note.id
    return {
        "content": [
            {"type": "text", "text": f"Saved note #{note_id}: {title!r}."}
        ]
    }


def build_app_mcp_server():
    """Create the in-process MCP server exposing the app's write-back tools."""
    return create_sdk_mcp_server(name=MCP_SERVER_NAME, tools=[save_note])
