# Persistent Claude CLI Session — Design

## Goal
Today every agent run cold-spawns a fresh `claude` CLI subprocess via the SDK's
one-shot `query()` (a `break` after the first `ResultMessage`). Use a single
**open, persistent** Claude CLI session, reused across runs, that **does not
time out** from the user's perspective: if the underlying session drops or
times out, it transparently reconnects so callers never see a dead session.

## Current architecture (what changes)
`app/agent/runner.py::stream_run` takes an injectable
`query_fn: Callable[..., AsyncIterator] = sdk_query`. Production callers
(`chat.py`, `capabilities.py`) use the default; **every test injects a fake
`query_fn`**. So we change only the default — the persistent session slots into
the existing seam, and all stubbed tests stay green untouched.

## Component: `app/agent/session.py`
A module-level singleton `ClaudeCliSession` wrapping one `ClaudeSDKClient`.

```python
def get_session() -> ClaudeCliSession   # process-wide singleton

class ClaudeCliSession:
    def __init__(self, client_factory=ClaudeSDKClient): ...
    async def run(self, *, prompt, options) -> AsyncIterator[Any]: ...
    async def start_keepalive(self) -> None
    async def stop(self) -> None
```

`run` matches `sdk_query`'s call shape (`prompt=`, `options=`) and yields the
same `AssistantMessage`/`ResultMessage` objects `stream_run` already parses, via
`client.query(prompt, session_id=...)` + `client.receive_response()`.

### Behaviors
1. **Reuse / warm:** first `run` connects the client; later runs reuse the live
   connection (no cold spawn). The connection is never closed between runs.
2. **Serialization:** an `asyncio.Lock` guards the single bidirectional stream —
   one run at a time. For a single-user local app, runs rarely overlap; queued
   execution satisfies the constitution's "concurrent runs MUST NOT corrupt
   state" (they queue, they don't interleave). Documented tradeoff.
3. **Per-run model:** call `client.set_model(options.model)` only when it differs
   from the currently-connected model (no redundant calls).
4. **api_key change:** if `options` carry a different `ANTHROPIC_API_KEY` (via
   `options.env`) than the session connected with, reconnect with the new
   options. Usually `None` (the app uses the user's logged-in CLI, no key).
5. **Reconnect-on-failure (the "no timeout" guarantee):** if `connect`/`query`/
   `receive_response` raises `CLIConnectionError` (or the client is not
   connected), the session reconnects once and retries the query before
   surfacing any error. A timed-out/dropped session self-heals on next use, so
   the caller never observes a timeout.
6. **Keep-alive heartbeat:** an optional background task (interval
   `agent_keep_alive_seconds`, default 120; `0` disables) that, under the lock,
   probes liveness (`client.get_server_info()`); if the probe raises, it
   reconnects. Proactively keeps the session warm so even the first request
   after a long idle is fast. Never raises into the app (best-effort).

### cwd tradeoff
One stable session cwd (`sessions_dir/"_live"`) instead of per-run
`sessions_dir/<run_id>`. Per-run cwd isolation is currently theoretical: `Read`
is denied in the tool allowlist and all artifacts are written through the
in-process MCP DB tools, not files. Documented; revisit if a skill ever ships
file-writing supporting tools.

## Wiring
- `runner.py`: add `async def live_query(*, prompt, options)` delegating to
  `get_session().run(prompt=prompt, options=options)`; change `stream_run`'s
  default `query_fn` from `sdk_query` to `live_query`. `sdk_query` stays imported
  for the one-shot fallback path inside the session.
- `app/main.py` lifespan: `await get_session().start_keepalive()` after
  `init_db()`; `await get_session().stop()` on shutdown (best-effort).
- `app/config.py`: add `agent_keep_alive_seconds: int = 120`.

## Out of scope (deferred, documented)
- Routing the one-shot synthesis calls (`profile_service`, `briefing_service`,
  `normalizer`) through the session. They are infrequent single turns and work
  cold; their `query_fn` seams are unchanged. Revisit if synthesis latency
  matters.
- A pool of warm sessions for true parallel runs. YAGNI for single-user.

## Testing
Deterministic unit tests inject a `FakeClient` (implements `connect`, `query`,
`receive_response` as a scripted async-gen, `set_model`, `get_server_info`,
`disconnect`) via `client_factory`:
- two runs → exactly one `connect` (reuse).
- `set_model` called when model changes, skipped when unchanged.
- first `query` raising `CLIConnectionError` → reconnect + retry → run still
  yields its scripted messages.
- keep-alive probe raising → triggers a reconnect.
- `run` yields scripted `AssistantMessage`/`ResultMessage` in order.
Live path stays behind the existing key-gated `*_live` probes. No backend
behavior other than connectivity transport changes; grounding/approval pipeline
untouched (Constitution III/IV).
