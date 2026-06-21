from __future__ import annotations

from pathlib import Path

from app import capabilities as caps
from app.models import Opportunity, OpportunityType, Profile

PACK_SKILLS_DIR = (
    Path(__file__).resolve().parent.parent / "skills" / "career-pack" / "skills"
)
BUSINESS_SKILLS_DIR = (
    Path(__file__).resolve().parent.parent / "skills" / "business-pack" / "skills"
)


def test_registry_has_the_expected_capabilities():
    assert set(caps.REGISTRY) == {
        # career-pack (slice A+D)
        "enrich-opportunity",
        "company-research",
        "company-enrich",
        "cv-tailor",
        "cover-letter",
        "interview-prep",
        "fit-analysis",
        # business-pack (slice F)
        "discover-opportunities",
        "qualify-opportunity",
        "analyze-opportunity",
        "draft-pursuit",
    }


def test_registry_skills_match_pack_directories():
    career_dirs = {p.name for p in PACK_SKILLS_DIR.iterdir() if p.is_dir()}
    business_dirs = {p.name for p in BUSINESS_SKILLS_DIR.iterdir() if p.is_dir()}
    assert {c.skill for c in caps.CAPABILITIES if c.plugin == "career-pack"} == career_dirs
    assert {c.skill for c in caps.CAPABILITIES if c.plugin == "business-pack"} == business_dirs


def test_skill_names_are_plugin_qualified():
    assert len(caps.SKILL_NAMES) == 11
    assert "career-pack:fit-analysis" in caps.SKILL_NAMES
    assert "business-pack:qualify-opportunity" in caps.SKILL_NAMES


def test_build_prompt_includes_opportunity_and_profile():
    cap = caps.REGISTRY["fit-analysis"]
    opp = Opportunity(
        type=OpportunityType.job, title="Staff ML Engineer",
        organization="Acme AI", summary="PyTorch platform team",
        dedupe_key="acme|staff-ml",
        details={"skills": ["pytorch"], "seniority": "staff"},
    )
    profile = Profile(headline="Staff ML engineer", skills=["pytorch", "k8s"])
    prompt = caps.build_prompt(cap, opportunity=opp, profile=profile)
    assert 'career-pack:fit-analysis' in prompt
    assert f"- id: {opp.id}" in prompt
    assert "Staff ML Engineer" in prompt and "Acme AI" in prompt
    assert "- dedupe_key: acme|staff-ml" in prompt
    assert "pytorch" in prompt
    assert '- details: {"seniority": "staff", "skills": ["pytorch"]}' in prompt


def test_build_prompt_profile_placeholder_when_missing():
    cap = caps.REGISTRY["cv-tailor"]
    opp = Opportunity(type=OpportunityType.job, title="Engineer")
    prompt = caps.build_prompt(cap, opportunity=opp, profile=None)
    assert "(no synthesized profile" in prompt


def test_build_prompt_enrich_carries_input_only():
    cap = caps.REGISTRY["enrich-opportunity"]
    prompt = caps.build_prompt(cap, input_text="We are hiring a Platform Engineer…")
    assert "Platform Engineer" in prompt
    assert "Opportunity:" not in prompt
    assert "Candidate profile" not in prompt


def test_build_prompt_uses_capability_plugin():
    cap = caps.REGISTRY["qualify-opportunity"]
    opp = Opportunity(
        type=OpportunityType.business, title="ML tooling grant",
        organization="GrantCo", dedupe_key="https://grants.example/ml",
        details={"opportunity_kind": "grant", "deadline": "2026-07-01"},
    )
    prompt = caps.build_prompt(cap, opportunity=opp, profile=None)
    assert '"business-pack:qualify-opportunity"' in prompt
    assert "ML tooling grant" in prompt
    assert '"opportunity_kind": "grant"' in prompt  # details JSON survives
    assert "Candidate profile" in prompt  # include_profile=True, placeholder when None
