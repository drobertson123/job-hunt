# Persistent Claude CLI Session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reuse one warm, persistent `claude` CLI session across agent runs that transparently reconnects on timeout/drop, instead of cold-spawning a subprocess per run.

**Architecture:** A singleton `ClaudeCliSession` wraps one `ClaudeSDKClient`, serialized by an `asyncio.Lock`, exposing an async-generator `run(*, prompt, options)` that matches the existing `sdk_query` call shape so it drops into `stream_run`'s injectable `query_fn` seam. It reconnects on `CLIConnectionError` and runs an optional keep-alive heartbeat.

**Tech Stack:** Python 3.12, claude-agent-sdk 0.2.x (`ClaudeSDKClient`, `CLIConnectionError`), FastAPI lifespan, pytest/asyncio.

## Global Constraints
- The persistent session is the new DEFAULT for `stream_run`'s `query_fn`. Every existing test injects its own `query_fn`/fakes, so they MUST stay green untouched.
- Serialized runs (one lock) are acceptable: single-user local app; queued, never interleaved → satisfies "concurrent runs MUST NOT corrupt state".
- No change to the grounding/approval pipeline, the MCP write-back tools, or message-parsing in `stream_run`.
- Tests are deterministic with an injected `FakeClient` (no real CLI/network/key). The live path stays behind the existing key-gated `*_live` probes.
- Verification: `bash scripts/ci/gate.sh` green (pytest). Run from the worktree; pytest uses `/home/drobertson123/src/job-hunt/.venv/bin/python`.
- Do NOT invoke any finishing/branch skill — implementers stop after committing and reporting.

---

### Task 1: `ClaudeCliSession` (reuse + reconnect + keep-alive) and config knob

**Files:**
- Modify: `app/config.py` (add `agent_keep_alive_seconds`)
- Create: `app/agent/session.py`
- Test: `tests/test_session.py`

**Interfaces:**
- Produces: `get_session() -> ClaudeCliSession`; `ClaudeCliSession(client_factory=ClaudeSDKClient)` with `async run(*, prompt, options) -> AsyncIterator[Any]`, `async start_keepalive(interval=None)`, `async stop()`, and a testable `async _probe()`.

- [ ] **Step 1: Add the config knob**

In `app/config.py`, in the "Agent safety caps" group (right after `agent_timeout_seconds: int = 300`), add:
```python
    # Persistent Claude CLI session: keep-alive probe interval (0 disables).
    agent_keep_alive_seconds: int = 120
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_session.py`:
```python
import pytest

from claude_agent_sdk import CLIConnectionError
from app.agent.session import ClaudeCliSession


class _Opts:
    """Minimal stand-in for ClaudeAgentOptions (only attrs the session reads)."""
    def __init__(self, model=None, api_key=None):
        self.model = model
        self.env = {"ANTHROPIC_API_KEY": api_key} if api_key else {}


class FakeClient:
    def __init__(self, options, script, fail_first_stream=False):
        self.options = options
        self.script = script
        self._fail = fail_first_stream
        self.connects = 0
        self.disconnects = 0
        self.set_models = []
        self.probes = 0
        self.server_info_raises = False

    async def connect(self):
        self.connects += 1

    async def disconnect(self):
        self.disconnects += 1

    async def set_model(self, model):
        self.set_models.append(model)

    async def get_server_info(self):
        self.probes += 1
        if self.server_info_raises:
            raise CLIConnectionError("dead")
        return {}

    async def query(self, prompt, session_id="default"):
        self._last_prompt = prompt

    async def receive_response(self):
        if self._fail:
            self._fail = False
            raise CLIConnectionError("dropped")
        for m in self.script:
            yield m


def _factory(script, fail_first=False):
    created = []

    def make(options):
        c = FakeClient(options, script, fail_first_stream=(fail_first and not created))
        created.append(c)
        return c

    return make, created


@pytest.mark.asyncio
async def test_run_yields_messages_in_order():
    script = ["a", "b", "RESULT"]
    make, created = _factory(script)
    s = ClaudeCliSession(client_factory=make)
    out = [m async for m in s.run(prompt="hi", options=_Opts(model="m1"))]
    assert out == script
    assert created[0].connects == 1


@pytest.mark.asyncio
async def test_second_run_reuses_connection():
    make, created = _factory(["RESULT"])
    s = ClaudeCliSession(client_factory=make)
    _ = [m async for m in s.run(prompt="1", options=_Opts(model="m1"))]
    _ = [m async for m in s.run(prompt="2", options=_Opts(model="m1"))]
    assert len(created) == 1          # connected once, reused
    assert created[0].connects == 1
    assert created[0].set_models == []  # same model → no set_model


@pytest.mark.asyncio
async def test_model_change_calls_set_model_without_reconnect():
    make, created = _factory(["RESULT"])
    s = ClaudeCliSession(client_factory=make)
    _ = [m async for m in s.run(prompt="1", options=_Opts(model="m1"))]
    _ = [m async for m in s.run(prompt="2", options=_Opts(model="m2"))]
    assert len(created) == 1
    assert created[0].set_models == ["m2"]


@pytest.mark.asyncio
async def test_reconnect_on_dropped_session():
    make, created = _factory(["RESULT"], fail_first=True)
    s = ClaudeCliSession(client_factory=make)
    out = [m async for m in s.run(prompt="hi", options=_Opts(model="m1"))]
    assert out == ["RESULT"]            # retried after reconnect
    assert len(created) == 2            # first failed, reconnected to a new client
    assert created[0].disconnects == 1


@pytest.mark.asyncio
async def test_api_key_change_reconnects():
    make, created = _factory(["RESULT"])
    s = ClaudeCliSession(client_factory=make)
    _ = [m async for m in s.run(prompt="1", options=_Opts(model="m1", api_key="k1"))]
    _ = [m async for m in s.run(prompt="2", options=_Opts(model="m1", api_key="k2"))]
    assert len(created) == 2            # key changed → reconnect


@pytest.mark.asyncio
async def test_probe_drops_dead_session():
    make, created = _factory(["RESULT"])
    s = ClaudeCliSession(client_factory=make)
    _ = [m async for m in s.run(prompt="1", options=_Opts(model="m1"))]
    created[0].server_info_raises = True
    await s._probe()
    assert created[0].disconnects == 1  # dead probe → session reset
    # next run reconnects
    _ = [m async for m in s.run(prompt="2", options=_Opts(model="m1"))]
    assert len(created) == 2
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_session.py -q`
Expected: FAIL (`ModuleNotFoundError: app.agent.session`).

- [ ] **Step 4: Implement `app/agent/session.py`**

```python
"""Persistent Claude CLI session — one warm ClaudeSDKClient reused across runs.

The agent runner historically cold-spawned a fresh `claude` CLI per run via the
SDK's one-shot `query()`. This keeps a single client connected and reuses it,
serialized by a lock, and transparently reconnects if the underlying session
drops or times out — so callers never observe a timed-out session.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from claude_agent_sdk import ClaudeSDKClient, CLIConnectionError

logger = logging.getLogger(__name__)


def _api_key_of(options: Any) -> str | None:
    env = getattr(options, "env", None) or {}
    return env.get("ANTHROPIC_API_KEY")


class ClaudeCliSession:
    """A single persistent Claude CLI client, reused across runs and lock-serialized."""

    def __init__(self, client_factory: Callable[[Any], Any] = ClaudeSDKClient) -> None:
        self._factory = client_factory
        self._client: Any | None = None
        self._lock = asyncio.Lock()
        self._model: str | None = None
        self._api_key: str | None = None
        self._keepalive_task: asyncio.Task[Any] | None = None

    async def _connect(self, options: Any) -> None:
        client = self._factory(options)
        await client.connect()
        self._client = client
        self._model = getattr(options, "model", None)
        self._api_key = _api_key_of(options)

    async def _reset(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:  # noqa: BLE001 — best effort
                pass
        self._client = None
        self._model = None
        self._api_key = None

    async def _ensure(self, options: Any) -> None:
        # Reconnect if never connected or the api key changed (env is fixed at connect).
        if self._client is None or _api_key_of(options) != self._api_key:
            await self._reset()
            await self._connect(options)
            return
        model = getattr(options, "model", None)
        if model and model != self._model:
            await self._client.set_model(model)
            self._model = model

    async def _stream(self, prompt: Any) -> AsyncIterator[Any]:
        await self._client.query(prompt)
        async for msg in self._client.receive_response():
            yield msg

    async def run(self, *, prompt: Any, options: Any) -> AsyncIterator[Any]:
        """Send one turn on the persistent session; reconnect+retry once on drop."""
        async with self._lock:
            yielded = False
            try:
                await self._ensure(options)
                async for msg in self._stream(prompt):
                    yielded = True
                    yield msg
            except CLIConnectionError:
                if yielded:
                    raise  # mid-turn failure — don't replay a partial turn
                logger.warning("Claude session dropped; reconnecting", exc_info=True)
                await self._reset()
                await self._connect(options)
                async for msg in self._stream(prompt):
                    yield msg

    async def _probe(self) -> None:
        """Liveness check for the keep-alive loop; drop a dead session so the next run reconnects."""
        async with self._lock:
            if self._client is None:
                return
            try:
                await self._client.get_server_info()
            except Exception:  # noqa: BLE001 — dead/timed-out
                logger.warning("keep-alive probe failed; dropping session", exc_info=True)
                await self._reset()

    async def start_keepalive(self, interval: int | None = None) -> None:
        from app.config import get_config

        secs = get_config().agent_keep_alive_seconds if interval is None else interval
        if secs <= 0 or self._keepalive_task is not None:
            return
        self._keepalive_task = asyncio.create_task(self._keepalive_loop(secs))

    async def _keepalive_loop(self, secs: int) -> None:
        while True:
            await asyncio.sleep(secs)
            await self._probe()

    async def stop(self) -> None:
        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001
                pass
            self._keepalive_task = None
        async with self._lock:
            await self._reset()


_session: ClaudeCliSession | None = None


def get_session() -> ClaudeCliSession:
    global _session
    if _session is None:
        _session = ClaudeCliSession()
    return _session
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_session.py -q`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add app/config.py app/agent/session.py tests/test_session.py
git commit -m "feat(agent): persistent Claude CLI session with reuse, reconnect, keep-alive"
```

---

### Task 2: Wire the session as the default and into the app lifespan

**Files:**
- Modify: `app/agent/runner.py` (default `query_fn` → `live_query`; drop unused `sdk_query` import)
- Modify: `app/main.py` (start/stop keep-alive in lifespan)
- Test: reuse existing `tests/test_agent.py` (green) + add one default-routing test

**Interfaces:**
- Consumes: `get_session()` from `app.agent.session`.
- Produces: `live_query(*, prompt, options)` in `runner.py` (async generator delegating to the session).

- [ ] **Step 1: Add a failing default-routing test**

Append to `tests/test_agent.py`:
```python
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
```
(Note: `live_query` calls `get_session()` at call time, so patching `app.agent.session.get_session` takes effect.)

- [ ] **Step 2: Run it to verify it fails**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_agent.py::test_stream_run_default_query_fn_uses_persistent_session -q`
Expected: FAIL (default is still `sdk_query`, `seen` never set).

- [ ] **Step 3: Wire `runner.py`**

In `app/agent/runner.py`:
1. Remove the now-unused import line `from claude_agent_sdk import query as sdk_query`.
2. Add an import near the other `app.agent` imports: `from app.agent.session import get_session`.
3. Define `live_query` ABOVE `stream_run` (e.g. right after `build_options`):
```python
async def live_query(*, prompt: Any, options: ClaudeAgentOptions) -> AsyncIterator[Any]:
    """Default query_fn: route the turn through the process-wide persistent session."""
    async for msg in get_session().run(prompt=prompt, options=options):
        yield msg
```
4. Change `stream_run`'s signature default from `query_fn: Callable[..., AsyncIterator[Any]] = sdk_query` to `query_fn: Callable[..., AsyncIterator[Any]] = live_query`.

- [ ] **Step 4: Run the routing test + the full agent suite**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_agent.py -q`
Expected: PASS (existing tests inject their own `query_fn`; the new one passes).

- [ ] **Step 5: Wire the app lifespan**

In `app/main.py`, replace the lifespan body so it starts/stops the keep-alive:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from app.agent.session import get_session

    await get_session().start_keepalive()
    try:
        yield
    finally:
        await get_session().stop()
```

- [ ] **Step 6: Run the full gate**

Run: `bash scripts/ci/gate.sh`
Expected: GATE PASSED (all backend tests green).

- [ ] **Step 7: Commit**

```bash
git add app/agent/runner.py app/main.py tests/test_agent.py
git commit -m "feat(agent): route agent runs through the persistent session + lifespan keep-alive"
```
