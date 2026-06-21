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
