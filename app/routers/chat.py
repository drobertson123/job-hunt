"""Chat endpoint — runs an agent session and streams its events as SSE.

The model + API key are resolved from settings *before* the stream starts
(so the long-lived stream doesn't hold the request's DB session). Each event
from the runner is emitted as a Server-Sent Event; the first event carries the
`run_id` the client can use to re-attach via /api/runs/{id}/events.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session

from app.agent.runner import stream_run
from app.db import get_session
from app import settings_service as ss

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    prompt: str


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@router.post("")
async def chat(body: ChatRequest, session: Session = Depends(get_session)) -> StreamingResponse:
    model = ss.resolve_agent_model(session)
    api_key = ss.resolve_anthropic_key(session)

    async def gen() -> AsyncIterator[str]:
        async for event in stream_run(body.prompt, model=model, api_key=api_key):
            yield _sse(event)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
