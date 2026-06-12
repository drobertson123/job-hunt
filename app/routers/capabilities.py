"""Capability endpoints — templated invocations of career-pack skills.

POST /api/capabilities/{name} builds the deterministic prompt from the
registry (app.capabilities) and streams an ordinary agent run as SSE — the
same machinery as /api/chat, so events persist and re-attach works.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app import capabilities as caps
from app import settings_service as ss
from app.agent.runner import stream_run
from app.db import get_session
from app.models import Opportunity, Profile

router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])


class CapabilityOut(BaseModel):
    name: str
    label: str
    description: str
    requires_opportunity: bool
    requires_input: bool


class InvokeRequest(BaseModel):
    opportunity_id: str | None = None
    input: str = ""


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@router.get("", response_model=list[CapabilityOut])
def list_capabilities() -> list[CapabilityOut]:
    return [
        CapabilityOut(
            name=c.name, label=c.label, description=c.description,
            requires_opportunity=c.requires_opportunity,
            requires_input=c.requires_input,
        )
        for c in caps.CAPABILITIES
    ]


@router.post("/{name}")
async def invoke(
    name: str, body: InvokeRequest, session: Session = Depends(get_session)
) -> StreamingResponse:
    cap = caps.REGISTRY.get(name)
    if cap is None:
        raise HTTPException(status_code=404, detail=f"unknown capability '{name}'")
    if cap.requires_input and not body.input.strip():
        raise HTTPException(
            status_code=422, detail=f"capability '{name}' requires input"
        )
    opportunity: Opportunity | None = None
    if cap.requires_opportunity:
        if not body.opportunity_id:
            raise HTTPException(
                status_code=422, detail=f"capability '{name}' requires opportunity_id"
            )
        opportunity = session.get(Opportunity, body.opportunity_id)
        if opportunity is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
    profile = (
        session.exec(select(Profile)).first() if cap.include_profile else None
    )
    prompt = caps.build_prompt(
        cap, opportunity=opportunity, input_text=body.input, profile=profile
    )
    model = ss.resolve_agent_model(session)
    api_key = ss.resolve_anthropic_key(session)

    async def gen() -> AsyncIterator[str]:
        async for event in stream_run(prompt, model=model, api_key=api_key):
            yield _sse(event)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
