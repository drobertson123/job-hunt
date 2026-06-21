"""Spine tests: the write-back tool, the permission gate, and the runner's
persist+stream+replay behavior — all without a live API key.

The advisor's key point: prove the *row appears with correct values*, not just
that something streamed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock
from sqlmodel import Session, select

from app.agent import runner
from app.agent.tools import SAVE_NOTE_TOOL, current_run_id, save_note
from app.db import engine
from app.models import Event, Note, Run, RunStatus


async def test_save_note_writes_correct_row():
    run = runner.create_run("seed", model=None)
    token = current_run_id.set(run.id)
    try:
        result = await save_note.handler({"title": "Lead", "body": "Acme is hiring"})
    finally:
        current_run_id.reset(token)

    assert "Saved note" in result["content"][0]["text"]
    with Session(engine) as s:
        note = s.exec(select(Note).where(Note.run_id == run.id)).one()
        assert note.title == "Lead"
        assert note.body == "Acme is hiring"
        assert note.run_id == run.id


async def test_gate_allows_only_allowlisted_tools():
    allow = await runner._gate(SAVE_NOTE_TOOL, {}, None)
    assert allow.behavior == "allow"
    for forbidden in ("Bash", "Write", "Edit", "mcp__app__delete_everything"):
        deny = await runner._gate(forbidden, {}, None)
        assert deny.behavior == "deny"


def _fake_agent(blocks, with_result=True):
    async def fake(*, prompt, options) -> AsyncIterator:  # noqa: ARG001
        yield AssistantMessage(content=blocks, model="fake-model")
        if with_result:
            yield ResultMessage(
                subtype="success",
                duration_ms=1,
                duration_api_ms=1,
                is_error=False,
                num_turns=1,
                session_id="sess",
                result="ok",
                total_cost_usd=0.0,
            )

    return fake


async def test_stream_run_persists_streams_and_replays():
    blocks = [
        TextBlock(text="Hello "),
        TextBlock(text="world"),
        ToolUseBlock(id="t1", name="save_note", input={"title": "x", "body": "y"}),
    ]
    events = [
        e async for e in runner.stream_run("hi", query_fn=_fake_agent(blocks))
    ]
    types = [e["type"] for e in events]
    assert types == ["status", "token", "token", "tool_use", "result", "status"]
    assert events[0]["content"] == "running"
    assert events[-1]["content"] == "completed"
    assert [e["seq"] for e in events] == list(range(len(events)))

    run_id = events[0]["run_id"]
    with Session(engine) as s:
        run = s.get(Run, run_id)
        assert run.status == RunStatus.completed
        persisted = s.exec(select(Event).where(Event.run_id == run_id)).all()
        assert len(persisted) == len(events)

    # Re-attach: replay from the persisted log matches the live stream.
    replay = runner.events_after(run_id, after_seq=-1)
    assert [e["type"] for e in replay] == types
    # Partial re-attach from a mid-point.
    assert [e["seq"] for e in runner.events_after(run_id, after_seq=2)] == [3, 4, 5]


async def test_stream_run_records_failure():
    async def boom(*, prompt, options):  # noqa: ARG001
        if False:
            yield  # make it an async generator
        raise RuntimeError("agent exploded")

    events = [e async for e in runner.stream_run("hi", query_fn=boom)]
    types = [e["type"] for e in events]
    assert types == ["status", "error"]
    assert "agent exploded" in events[-1]["content"]

    run_id = events[0]["run_id"]
    with Session(engine) as s:
        assert s.get(Run, run_id).status == RunStatus.failed


@pytest.mark.asyncio
async def test_stream_run_default_query_fn_uses_persistent_session(monkeypatch):
    """With no query_fn injected, stream_run routes through the persistent session."""
    import app.agent.runner as runner_mod

    seen = {}

    async def fake_session_run(*, prompt, options):
        seen["called"] = True
        yield  # no messages; just prove the path is taken

    class FakeSession:
        run = staticmethod(fake_session_run)

    monkeypatch.setattr("app.agent.session.get_session", lambda: FakeSession())
    events = [e async for e in runner_mod.stream_run("ping")]
    assert seen.get("called") is True
    assert any(e["type"] == "status" for e in events)
