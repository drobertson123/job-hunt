"""Briefing synthesis: read an opportunity (+ company + corpus) and write a
structured Briefing row of answers to expected questions.

Mirrors profile_service: single-turn, tool-less local Claude CLI session
(Agent SDK, CLI auth — no API key), JSON validated by Pydantic, injectable
query_fn for tests.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock
from claude_agent_sdk import query as sdk_query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.config import get_config
from app.models import (
    Briefing,
    BriefingFactKey,
    Company,
    Document,
    Opportunity,
    _utcnow,
)

_CORPUS_CHAR_BUDGET = 12000


class FactSchema(BaseModel):
    key: BriefingFactKey = BriefingFactKey.other
    question: str
    answer: str
    confidence: float | None = None
    source: str | None = None


class BriefingSchema(BaseModel):
    summary: str = ""
    facts: list[FactSchema] = Field(default_factory=list)


_EXPECTED = ", ".join(k.value for k in BriefingFactKey if k != BriefingFactKey.other)

_INSTRUCTION = (
    "You build a concise briefing about a single job opportunity for the "
    "candidate. Answer these expected questions when the context supports them: "
    f"{_EXPECTED}. Tag each fact with the matching `key` (use \"other\" for "
    "anything extra). Ground why_fit and concerns in the candidate's own "
    "documents. Give each fact a confidence in [0,1] and a source. NEVER invent "
    "specifics (salary numbers, policies, names): if a fact is not supported by "
    "the context, give it a low confidence and a null source — never invent."
)


def _build_prompt(opp_text: str, corpus_text: str) -> str:
    schema = json.dumps(BriefingSchema.model_json_schema())
    return (
        f"{_INSTRUCTION}\n\n"
        "Respond with ONE JSON object and nothing else — no prose, no code fences. "
        f"It must conform to this JSON Schema:\n{schema}\n\n"
        "The opportunity (and company):\n"
        f"<opportunity>\n{opp_text}\n</opportunity>\n\n"
        "The candidate's documents:\n"
        f"<corpus>\n{corpus_text}\n</corpus>"
    )


def _extract_json(text: str) -> str:
    s = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        return s[start : end + 1]
    return s


def _opportunity_text(session: Session, opp: Opportunity) -> str:
    parts = [f"Title: {opp.title}"]
    if opp.organization:
        parts.append(f"Organization: {opp.organization}")
    if opp.location:
        parts.append(f"Location: {opp.location}")
    if opp.summary:
        parts.append(f"Summary: {opp.summary}")
    if opp.details:
        parts.append(f"Details: {json.dumps(opp.details)}")
    if opp.company_id:
        company = session.get(Company, opp.company_id)
        if company:
            extra = ""
            if company.industry:
                extra += f" — industry {company.industry}"
            if company.summary:
                extra += f"; {company.summary}"
            parts.append(f"Company: {company.name}{extra}")
    return "\n".join(parts)


async def synthesize_briefing(
    session: Session,
    *,
    opportunity_id: str,
    generated_run_id: str | None = None,
    query_fn: Callable[..., AsyncIterator[Any]] = sdk_query,
) -> Briefing:
    opp = session.get(Opportunity, opportunity_id)
    if opp is None:
        raise ValueError(f"opportunity {opportunity_id} not found")
    opp_text = _opportunity_text(session, opp)
    docs = session.exec(select(Document).order_by(Document.created_at)).all()
    corpus_text = "\n\n".join(
        f"# {d.title}\n{d.raw_text}" for d in docs
    )[:_CORPUS_CHAR_BUDGET]
    prompt = _build_prompt(opp_text, corpus_text)

    model = get_config().default_agent_model
    options = ClaudeAgentOptions(model=model, max_turns=1)
    chunks: list[str] = []
    async for message in query_fn(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock) and block.text:
                    chunks.append(block.text)
    parsed = BriefingSchema.model_validate_json(_extract_json("".join(chunks)))

    row = session.exec(
        select(Briefing).where(Briefing.opportunity_id == opportunity_id)
    ).first()
    if row is None:
        row = Briefing(opportunity_id=opportunity_id)
    row.company_id = opp.company_id
    row.summary = parsed.summary
    row.facts = [f.model_dump(mode="json") for f in parsed.facts]
    row.source_hash = hashlib.sha256(prompt.encode()).hexdigest()
    row.generated_run_id = generated_run_id
    row.refreshed_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_briefing(session: Session, opportunity_id: str) -> Briefing | None:
    return session.exec(
        select(Briefing).where(Briefing.opportunity_id == opportunity_id)
    ).first()
