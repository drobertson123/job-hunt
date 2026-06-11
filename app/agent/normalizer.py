"""Reused-skill normalizer — free-form markdown artifact -> structured job rows.

Reused MIT skills (e.g. the career-helper) emit free-form markdown, NOT calls to
our in-process MCP write-back tools. This module converts that free-form output
into structured `Opportunity` rows via a single Anthropic `messages.parse` call,
then persists them through the same service layer the authored-skill seam uses.

The module is DB-decoupled: `normalize_artifact` takes an injectable client and a
model name (defaulting to the configured agent model) so it is trivially testable
and carries no database dependency. `persist_normalized` is the only DB-aware part.
"""

from __future__ import annotations

import re
from typing import Any

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
    return (
        f"{_SYSTEM_INSTRUCTION}\n\n"
        "Here is the artifact between the markers:\n"
        "<artifact>\n"
        f"{markdown}\n"
        "</artifact>"
    )


def _default_client() -> Any:
    import anthropic

    return anthropic.Anthropic()


def normalize_artifact(
    markdown: str,
    *,
    client: Any | None = None,
    model: str | None = None,
    max_tokens: int = 2048,
) -> NormalizerResult:
    """Run one free-form artifact through messages.parse into a NormalizerResult.

    `client` is injectable (tests pass a fake exposing `.messages.parse`). `model`
    defaults to the configured agent model; the normalizer holds no DB dependency.
    """
    if client is None:
        client = _default_client()
    if model is None:
        model = get_config().default_agent_model

    response = client.messages.parse(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": _build_prompt(markdown)}],
        output_format=NormalizerResult,
    )
    return response.parsed_output


# Placeholder — replaced with real implementation in Task 4.
def persist_normalized(*args: Any, **kwargs: Any) -> "list[Opportunity]":
    raise NotImplementedError("implemented in Task 4")
