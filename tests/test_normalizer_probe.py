"""Normalizer probe — reused-skill free-form artifact -> structured job rows.

Two layers:
  * deterministic plumbing tests (stubbed client) — no API key needed;
  * a live probe (real messages.parse) that auto-skips without ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app.agent.normalizer import (
    JobDetails,
    NormalizedJob,
    NormalizerResult,
    dedupe_key_for,
    normalize_artifact,
    persist_normalized,
)
from app.db import engine
from app.models import Opportunity, OpportunityType

FIXTURE = Path(__file__).parent / "fixtures" / "career_helper_research_brief.md"


def test_dedupe_key_prefers_explicit_then_falls_back_to_org_title_slug():
    explicit = NormalizedJob(title="X", organization="Y", dedupe_key="given-key")
    assert dedupe_key_for(explicit) == "given-key"

    derived = NormalizedJob(title="Staff ML Engineer", organization="Acme AI")
    assert dedupe_key_for(derived) == "acme-ai-staff-ml-engineer"

    title_only = NormalizedJob(title="Solo Role!!")
    assert dedupe_key_for(title_only) == "solo-role"


def test_schema_defaults():
    job = NormalizedJob(title="Only Title")
    assert job.source == "career-helper"
    assert job.dedupe_key is None
    assert isinstance(job.details, JobDetails)
    assert job.details.skills == []
    assert NormalizerResult().opportunities == []
