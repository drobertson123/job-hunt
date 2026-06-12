"""Capability registry — named, templated invocations of career-pack skills.

A capability wraps ONE authored skill in a deterministic prompt: the UI (or
any client) POSTs /api/capabilities/{name} and the backend builds the exact
prompt naming the plugin-qualified skill, so invocation never depends on
free-form chat phrasing. Free-form chat can still trigger the same skills
naturally — the registry is the reliable path, not the only one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.models import Opportunity, Profile

PLUGIN_NAME = "career-pack"


@dataclass(frozen=True)
class Capability:
    name: str  # URL slug / UI identity (same as the skill directory name)
    skill: str  # SKILL.md `name` inside the plugin
    label: str
    description: str
    requires_opportunity: bool
    requires_input: bool
    include_profile: bool  # inline the synthesized Profile row into the prompt


CAPABILITIES = [
    Capability(
        name="enrich-opportunity",
        skill="enrich-opportunity",
        label="Add by paste",
        description="Paste a job posting; extract it into a pipeline opportunity.",
        requires_opportunity=False,
        requires_input=True,
        include_profile=False,
    ),
    Capability(
        name="company-research",
        skill="company-research",
        label="Company research",
        description="Research the company behind an opportunity into a sourced brief.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=False,
    ),
    Capability(
        name="cv-tailor",
        skill="cv-tailor",
        label="Tailor CV",
        description="Corpus-grounded, ATS-friendly CV for an opportunity.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=True,
    ),
    Capability(
        name="interview-prep",
        skill="interview-prep",
        label="Interview prep",
        description="Prep doc with grounded STAR stories and questions to ask.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=True,
    ),
    Capability(
        name="fit-analysis",
        skill="fit-analysis",
        label="Fit analysis",
        description="Re-runnable scored fit analysis of your profile vs the opportunity.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=True,
    ),
]

REGISTRY: dict[str, Capability] = {c.name: c for c in CAPABILITIES}

# Plugin-qualified names for ClaudeAgentOptions.skills.
SKILL_NAMES = [f"{PLUGIN_NAME}:{c.skill}" for c in CAPABILITIES]


def opportunity_block(opp: Opportunity) -> str:
    lines = [f"- id: {opp.id}", f"- title: {opp.title}"]
    if opp.organization:
        lines.append(f"- organization: {opp.organization}")
    if opp.url:
        lines.append(f"- url: {opp.url}")
    if opp.location:
        lines.append(f"- location: {opp.location}")
    if opp.summary:
        lines.append(f"- summary: {opp.summary}")
    if opp.dedupe_key:
        lines.append(f"- dedupe_key: {opp.dedupe_key}")
    if opp.details:
        lines.append(f"- details: {json.dumps(opp.details, sort_keys=True)}")
    return "\n".join(lines)


def profile_block(profile: Profile | None) -> str:
    if profile is None:
        return "- (no synthesized profile — use mcp__app__search_corpus instead)"
    # experience/achievements deliberately omitted: STAR stories and bullets come from corpus search per the skills' grounding rules; inlining them would bloat every prompt.
    lines = []
    if profile.headline:
        lines.append(f"- headline: {profile.headline}")
    if profile.summary:
        lines.append(f"- summary: {profile.summary}")
    if profile.skills:
        lines.append(f"- skills: {', '.join(profile.skills)}")
    if profile.target_titles:
        lines.append(f"- target titles: {', '.join(profile.target_titles)}")
    if profile.locations:
        lines.append(f"- locations: {', '.join(profile.locations)}")
    return "\n".join(lines) or "- (empty profile)"


def build_prompt(
    cap: Capability,
    *,
    opportunity: Opportunity | None = None,
    input_text: str = "",
    profile: Profile | None = None,
) -> str:
    parts = [
        f'Use the "{PLUGIN_NAME}:{cap.skill}" skill now (via the Skill tool), '
        "then follow its write-back contract exactly."
    ]
    if opportunity is not None:
        parts.append("Opportunity:\n" + opportunity_block(opportunity))
    if cap.include_profile:
        parts.append("Candidate profile (synthesized):\n" + profile_block(profile))
    if input_text.strip():
        parts.append("Input:\n" + input_text.strip())
    return "\n\n".join(parts)
