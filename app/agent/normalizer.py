"""Reused-skill normalizer — free-form markdown artifact -> structured job rows.

Reused MIT skills (e.g. the career-helper) emit free-form markdown, NOT calls to
our in-process MCP write-back tools. This module converts that free-form output
into structured `Opportunity` rows, then persists them through the same service
layer the authored-skill seam uses.

Auth/mechanism (decided 2026-06-11): extraction runs through the local Claude
Agent SDK session — the same `claude` CLI auth Phase 0 uses — NOT the Anthropic
API. There is therefore no `messages.parse` structured-output guarantee: we
prompt for a JSON object matching `NormalizerResult`'s schema, then parse and
validate it ourselves with Pydantic. `query_fn` is injectable (mirroring
`runner.stream_run`) so deterministic tests run with no CLI / network / key.
`persist_normalized` is the only DB-aware part.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock
from claude_agent_sdk import query as sdk_query
from pydantic import BaseModel, Field
from sqlmodel import Session

from app import services
from app.config import get_config
from app.models import Opportunity, OpportunityType


class JobDetails(BaseModel):
    """Type-specific job fields, mirrored from the Opportunity.details convention."""

    salary: str | None = None
    seniority: str | None = None
    employment_type: str | None = None
    skills: list[str] = Field(default_factory=list)


class NormalizedJob(BaseModel):
    """One job opportunity extracted from a free-form artifact.

    Field names map 1:1 onto services.upsert_opportunity keyword arguments.
    """

    title: str
    organization: str | None = None
    url: str | None = None
    location: str | None = None
    summary: str | None = None
    source: str = "career-helper"
    dedupe_key: str | None = None
    details: JobDetails = Field(default_factory=JobDetails)


class NormalizerResult(BaseModel):
    """Top-level structured-output schema: zero or more job opportunities."""

    opportunities: list[NormalizedJob] = Field(default_factory=list)


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _SLUG_RE.sub("-", text.strip().lower()).strip("-")


def dedupe_key_for(job: NormalizedJob) -> str:
    """Stable idempotency key: explicit key wins, else org+title slug, else title slug."""
    if job.dedupe_key:
        return job.dedupe_key
    parts = [p for p in (job.organization, job.title) if p]
    return _slug(" ".join(parts)) if parts else _slug(job.title)


_SYSTEM_INSTRUCTION = (
    "You convert a free-form career research artifact into structured job "
    "opportunities. Extract every distinct role described. For each, capture the "
    "role title, hiring organization, location, a one-paragraph summary, and any "
    "job details present (salary, seniority, employment type, key skills). If a "
    "field is absent in the artifact, omit it — never invent values."
)


def _build_prompt(markdown: str) -> str:
    schema = json.dumps(NormalizerResult.model_json_schema())
    return (
        f"{_SYSTEM_INSTRUCTION}\n\n"
        "Respond with ONE JSON object and nothing else — no prose, no code "
        "fences, no explanation. It must conform to this JSON Schema:\n"
        f"{schema}\n\n"
        "Here is the artifact between the markers:\n"
        "<artifact>\n"
        f"{markdown}\n"
        "</artifact>"
    )


def _extract_json(text: str) -> str:
    """Pull the JSON object out of a free-form model reply.

    The CLI may wrap the object in ```json fences or surround it with prose, so we
    strip fences first, then fall back to slicing between the outermost braces.
    """
    s = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        return s[start : end + 1]
    return s


async def normalize_artifact(
    markdown: str,
    *,
    query_fn: Callable[..., AsyncIterator[Any]] = sdk_query,
    model: str | None = None,
) -> NormalizerResult:
    """Run one free-form artifact through a local CLI session into a NormalizerResult.

    Drives a single-turn `claude` Agent SDK query (no tools, CLI auth — no API
    key), concatenates the assistant's text, then parses + validates the JSON
    ourselves. `query_fn` is injectable; `model` defaults to the configured agent
    model. Holds no DB dependency.
    """
    if model is None:
        model = get_config().default_agent_model

    options = ClaudeAgentOptions(model=model, max_turns=1)
    chunks: list[str] = []
    async for message in query_fn(prompt=_build_prompt(markdown), options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock) and block.text:
                    chunks.append(block.text)

    return NormalizerResult.model_validate_json(_extract_json("".join(chunks)))


def persist_normalized(
    session: Session,
    result: NormalizerResult,
    *,
    source: str | None = None,
) -> list[Opportunity]:
    """Persist each normalized job as a `job` Opportunity via the service layer.

    Returns the upserted rows. `details` is dumped to a plain dict (dropping unset
    fields) so the Opportunity.details JSON column receives a free-form mapping.
    """
    rows: list[Opportunity] = []
    for job in result.opportunities:
        details = job.details.model_dump(exclude_none=True, exclude_defaults=True)
        opp = services.upsert_opportunity(
            session,
            type=OpportunityType.job,
            title=job.title,
            dedupe_key=dedupe_key_for(job),
            organization=job.organization,
            url=job.url,
            location=job.location,
            summary=job.summary,
            source=source or job.source,
            details=details,
        )
        rows.append(opp)
    return rows
