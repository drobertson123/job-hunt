from __future__ import annotations

from pathlib import Path

from app import capabilities as caps
from app.models import Opportunity, OpportunityType, Profile

PACK_SKILLS_DIR = (
    Path(__file__).resolve().parent.parent / "skills" / "career-pack" / "skills"
)


def test_registry_has_the_five_capabilities():
    assert set(caps.REGISTRY) == {
        "enrich-opportunity",
        "company-research",
        "cv-tailor",
        "interview-prep",
        "fit-analysis",
    }


def test_registry_skills_match_pack_directories():
    dirs = {p.name for p in PACK_SKILLS_DIR.iterdir() if p.is_dir()}
    assert {c.skill for c in caps.CAPABILITIES} == dirs


def test_skill_names_are_plugin_qualified():
    assert len(caps.SKILL_NAMES) == 5
    assert "career-pack:fit-analysis" in caps.SKILL_NAMES


def test_build_prompt_includes_opportunity_and_profile():
    cap = caps.REGISTRY["fit-analysis"]
    opp = Opportunity(
        type=OpportunityType.job, title="Staff ML Engineer",
        organization="Acme AI", summary="PyTorch platform team",
        dedupe_key="acme|staff-ml",
    )
    profile = Profile(headline="Staff ML engineer", skills=["pytorch", "k8s"])
    prompt = caps.build_prompt(cap, opportunity=opp, profile=profile)
    assert 'career-pack:fit-analysis' in prompt
    assert f"- id: {opp.id}" in prompt
    assert "Staff ML Engineer" in prompt and "Acme AI" in prompt
    assert "- dedupe_key: acme|staff-ml" in prompt
    assert "pytorch" in prompt


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
