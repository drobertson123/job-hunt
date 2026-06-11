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


# Placeholders — replaced with real implementations in Tasks 3 and 4.
def normalize_artifact(*args: Any, **kwargs: Any) -> "NormalizerResult":  # noqa: D401
    raise NotImplementedError("implemented in Task 3")


def persist_normalized(*args: Any, **kwargs: Any) -> "list[Opportunity]":
    raise NotImplementedError("implemented in Task 4")
