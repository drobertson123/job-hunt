"""Agent runner — drives a local Claude Agent SDK session and persists its events.

Design notes (Phase 0):
  * `stream_run` is an async generator. It creates a durable Run row, then for
    every SDK message persists an Event (append-only, monotonic `seq`) AND yields
    it. The persisted log is the source of truth, so a client that drops mid-run
    (a phone that slept) can re-attach by replaying events after its last seq.
  * The agent's tool surface is locked to our allowlist via a `can_use_tool`
    gate that denies everything else — defense-in-depth against prompt-injection
    tool-abuse. Phase 0's only tool is the in-process `save_note`.
  * `query_fn` is injectable so tests exercise the whole pipeline with a fake
    agent (no live API key / network).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from claude_agent_sdk import query as sdk_query
from sqlmodel import Session

from app.agent.tools import (
    ALL_TOOL_NAMES,
    MCP_SERVER_NAME,
    build_app_mcp_server,
    current_run_id,
)
from app.capabilities import SKILL_NAMES
from app.config import get_config
from app.db import engine
from app.models import Event, EventType, Run, RunStatus

# The agent may call our in-process write-back tools, the Skill tool (career
# pack), Read (skills' supporting files), and web research tools. The gate
# below denies everything else (ToolSearch, a benign discovery meta-tool, is
# exempt by the SDK and is what lets the agent find these mcp__app__* tools).
ALLOWED_TOOLS = [*ALL_TOOL_NAMES, "Skill", "Read", "WebSearch", "WebFetch"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _gate(tool_name: str, _input: dict[str, Any], _ctx: Any):
    """can_use_tool: allow only allowlisted tools; deny everything else."""
    if tool_name in ALLOWED_TOOLS:
        return PermissionResultAllow()
    return PermissionResultDeny(
        message=f"Tool '{tool_name}' is not permitted in this workspace.",
    )


async def _as_stream(prompt: str) -> AsyncIterator[dict[str, Any]]:
    """Wrap a single prompt as streaming input.

    The SDK requires AsyncIterable input (not a bare string) whenever a
    `can_use_tool` callback is set, so our permission gate forces this mode.
    """
    yield {"type": "user", "message": {"role": "user", "content": prompt}}


def build_options(*, model: str | None, cwd: Path, api_key: str | None) -> ClaudeAgentOptions:
    cfg = get_config()
    env: dict[str, str] = {}
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    return ClaudeAgentOptions(
        model=model,
        mcp_servers={MCP_SERVER_NAME: build_app_mcp_server()},
        allowed_tools=ALLOWED_TOOLS,
        can_use_tool=_gate,
        permission_mode="default",
        max_turns=cfg.agent_max_turns,
        cwd=str(cwd),
        env=env,
        # Authored skills ship as a repo-local plugin with an ABSOLUTE path —
        # per-run cwd isolation stays intact and discovery can't silently
        # find zero skills. `skills=` is the SDK's single enablement knob
        # (auto-configures the Skill tool); setting_sources stays None.
        plugins=[{"type": "local", "path": str(cfg.career_pack_dir)}],
        skills=list(SKILL_NAMES),
        setting_sources=None,
    )


def _persist(run_id: str, seq: int, etype: EventType, content: str = "") -> None:
    with Session(engine) as session:
        session.add(Event(run_id=run_id, seq=seq, type=etype, content=content))
        session.commit()


def _set_run_status(run_id: str, status: RunStatus, error: str | None = None) -> None:
    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None:
            return
        run.status = status
        run.updated_at = _utcnow()
        if error is not None:
            run.error = error
        session.add(run)
        session.commit()


def create_run(prompt: str, model: str | None) -> Run:
    cfg = get_config()
    with Session(engine) as session:
        run = Run(prompt=prompt, model=model, status=RunStatus.pending)
        session.add(run)
        session.commit()
        session.refresh(run)
        # per-session working dir for file isolation
        cwd = cfg.sessions_dir / run.id
        cwd.mkdir(parents=True, exist_ok=True)
        run.cwd = str(cwd)
        session.add(run)
        session.commit()
        session.refresh(run)
        return run


async def stream_run(
    prompt: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
    run: Run | None = None,
    query_fn: Callable[..., AsyncIterator[Any]] = sdk_query,
) -> AsyncIterator[dict[str, Any]]:
    """Run an agent query, persisting + yielding each event as a dict."""
    if run is None:
        run = create_run(prompt, model)
    run_id = run.id
    cwd = Path(run.cwd) if run.cwd else get_config().sessions_dir / run_id
    seq = 0

    def emit(etype: EventType, content: str) -> dict[str, Any]:
        nonlocal seq
        _persist(run_id, seq, etype, content)
        event = {"run_id": run_id, "seq": seq, "type": etype.value, "content": content}
        seq += 1
        return event

    token = current_run_id.set(run_id)
    _set_run_status(run_id, RunStatus.running)
    yield emit(EventType.status, RunStatus.running.value)

    try:
        options = build_options(model=model, cwd=cwd, api_key=api_key)
        async for message in query_fn(prompt=_as_stream(prompt), options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        if block.text:
                            yield emit(EventType.token, block.text)
                    elif isinstance(block, ToolUseBlock):
                        yield emit(
                            EventType.tool_use,
                            json.dumps({"name": block.name, "input": block.input}),
                        )
                    elif isinstance(block, ToolResultBlock):
                        content = block.content
                        text = content if isinstance(content, str) else json.dumps(content)
                        yield emit(EventType.tool_result, text or "")
            elif isinstance(message, ResultMessage):
                payload = {
                    "result": message.result,
                    "is_error": message.is_error,
                    "total_cost_usd": message.total_cost_usd,
                    "num_turns": message.num_turns,
                }
                yield emit(EventType.result, json.dumps(payload))
                break  # one-shot: stop after the turn completes (streaming-input mode)
        _set_run_status(run_id, RunStatus.completed)
        yield emit(EventType.status, RunStatus.completed.value)
    except Exception as exc:  # noqa: BLE001 - surface any failure as an event
        _set_run_status(run_id, RunStatus.failed, error=str(exc))
        yield emit(EventType.error, str(exc))
    finally:
        current_run_id.reset(token)


def events_after(run_id: str, after_seq: int = -1) -> list[dict[str, Any]]:
    """Replay persisted events (for re-attach after a dropped connection)."""
    from sqlmodel import select

    with Session(engine) as session:
        rows = session.exec(
            select(Event)
            .where(Event.run_id == run_id, Event.seq > after_seq)
            .order_by(Event.seq)
        ).all()
        return [
            {"run_id": r.run_id, "seq": r.seq, "type": r.type.value, "content": r.content}
            for r in rows
        ]
