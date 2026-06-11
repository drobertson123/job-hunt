# app/profile_service.py
"""Profile synthesis: read the corpus broadly and write a structured Profile row.

Reuses the normalizer's mechanism: a single-turn, tool-less local Claude CLI
session (Agent SDK, CLI auth — no API key), with JSON validated by Pydantic.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock
from claude_agent_sdk import query as sdk_query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.config import get_config
from app.models import Document, Profile, _utcnow

_CORPUS_CHAR_BUDGET = 24000


class ProfileSchema(BaseModel):
    headline: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[dict] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    target_titles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)


_INSTRUCTION = (
    "You build a structured career profile of a single person from their own "
    "documents. Use ONLY what the documents support. If a field is not evidenced, "
    "leave it empty — never invent experience, employers, titles, or skills."
)


def _build_prompt(corpus_text: str) -> str:
    schema = json.dumps(ProfileSchema.model_json_schema())
    return (
        f"{_INSTRUCTION}\n\n"
        "Respond with ONE JSON object and nothing else — no prose, no code fences. "
        f"It must conform to this JSON Schema:\n{schema}\n\n"
        "Here are the person's documents between the markers:\n"
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


async def synthesize_profile(
    session: Session,
    *,
    query_fn: Callable[..., AsyncIterator[Any]] = sdk_query,
) -> Profile:
    """Synthesize and persist (overwrite) the single Profile row from the corpus."""
    docs = session.exec(select(Document).order_by(Document.created_at)).all()
    if not docs:
        raise ValueError("corpus is empty; nothing to synthesize")
    # Hard char budget keeps the single-turn prompt bounded; the last included
    # document may be cut mid-text, which is acceptable for synthesis.
    corpus_text = "\n\n".join(f"# {d.title}\n{d.raw_text}" for d in docs)[:_CORPUS_CHAR_BUDGET]

    model = get_config().default_agent_model
    options = ClaudeAgentOptions(model=model, max_turns=1)
    chunks: list[str] = []
    async for message in query_fn(prompt=_build_prompt(corpus_text), options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock) and block.text:
                    chunks.append(block.text)
    parsed = ProfileSchema.model_validate_json(_extract_json("".join(chunks)))

    row = session.exec(select(Profile)).first()
    if row is None:
        row = Profile()
    row.headline = parsed.headline
    row.summary = parsed.summary
    row.skills = parsed.skills
    row.experience = parsed.experience
    row.achievements = parsed.achievements
    row.target_titles = parsed.target_titles
    row.locations = parsed.locations
    row.source_doc_count = len(docs)
    row.synthesized_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
