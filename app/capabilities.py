"""Capability registry — named, templated invocations of authored-pack skills.

A capability wraps ONE authored skill in a deterministic prompt: the UI (or
any client) POSTs /api/capabilities/{name} and the backend builds the exact
prompt naming the plugin-qualified skill, so invocation never depends on
free-form chat phrasing. Free-form chat can still trigger the same skills
naturally — the registry is the reliable path, not the only one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.models import Contact, Opportunity, Profile

CAREER_PLUGIN = "career-pack"
BUSINESS_PLUGIN = "business-pack"


@dataclass(frozen=True)
class Capability:
    name: str  # URL slug / UI identity (same as the skill directory name)
    skill: str  # SKILL.md `name` inside the plugin
    label: str
    description: str
    requires_opportunity: bool
    requires_input: bool
    include_profile: bool  # inline the synthesized Profile row into the prompt
    plugin: str  # which authored pack ships the skill (qualified name prefix)
    include_preferences: bool = False  # inline job preferences into the prompt
    include_contacts: bool = False  # inline the user's contacts into the prompt


CAPABILITIES = [
    Capability(
        name="enrich-opportunity",
        skill="enrich-opportunity",
        label="Add by paste",
        description="Paste a job posting; extract it into a pipeline opportunity.",
        requires_opportunity=False,
        requires_input=True,
        include_profile=False,
        plugin=CAREER_PLUGIN,
    ),
    Capability(
        name="company-research",
        skill="company-research",
        label="Company research",
        description="Research the company behind an opportunity into a sourced brief.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=False,
        plugin=CAREER_PLUGIN,
    ),
    Capability(
        name="company-enrich",
        skill="company-enrich",
        label="Enrich company",
        description="Research the company behind an opportunity into its structured profile.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=False,
        plugin=CAREER_PLUGIN,
    ),
    Capability(
        name="cv-tailor",
        skill="cv-tailor",
        label="Tailor CV",
        description="Corpus-grounded, ATS-friendly CV for an opportunity.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=True,
        plugin=CAREER_PLUGIN,
    ),
    Capability(
        name="cover-letter",
        skill="cover-letter",
        label="Cover letter",
        description="Corpus-grounded cover letter for an opportunity.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=True,
        plugin=CAREER_PLUGIN,
    ),
    Capability(
        name="interview-prep",
        skill="interview-prep",
        label="Interview prep",
        description="Prep doc with grounded STAR stories and questions to ask.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=True,
        plugin=CAREER_PLUGIN,
    ),
    Capability(
        name="fit-analysis",
        skill="fit-analysis",
        label="Fit analysis",
        description="Re-runnable scored fit analysis of your profile vs the opportunity.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=True,
        plugin=CAREER_PLUGIN,
        include_preferences=True,
    ),
    Capability(
        name="email-analyser",
        skill="email-analyser",
        label="Analyse email",
        description="Paste an email about an opportunity; log it as a communication and capture follow-ups.",
        requires_opportunity=True,
        requires_input=True,
        include_profile=False,
        plugin=CAREER_PLUGIN,
    ),
    Capability(
        name="sms-analyser",
        skill="sms-analyser",
        label="Analyse text",
        description="Paste a text message about an opportunity; log it and capture follow-ups.",
        requires_opportunity=True,
        requires_input=True,
        include_profile=False,
        plugin=CAREER_PLUGIN,
    ),
    Capability(
        name="apply-prep",
        skill="apply-prep",
        label="Apply prep",
        description="Assemble an application kit (docs checklist + ATS field guidance) for an opportunity.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=True,
        plugin=CAREER_PLUGIN,
    ),
    Capability(
        name="network-scan",
        skill="network-scan",
        label="Network scan",
        description="Scan your contacts' companies for matching openings (warm intros).",
        requires_opportunity=False,
        requires_input=False,
        include_profile=True,
        plugin=CAREER_PLUGIN,
        include_contacts=True,
    ),
    Capability(
        name="discover-opportunities",
        skill="discover-opportunities",
        label="Discover",
        description="Web sweep for business opportunities (RFPs, grants, leads) matching your profile.",
        requires_opportunity=False,
        requires_input=False,
        include_profile=True,
        plugin=BUSINESS_PLUGIN,
    ),
    Capability(
        name="qualify-opportunity",
        skill="qualify-opportunity",
        label="Qualify",
        description="Qualify a business opportunity: move its stage with evidence and record the decision.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=True,
        plugin=BUSINESS_PLUGIN,
    ),
    Capability(
        name="analyze-opportunity",
        skill="analyze-opportunity",
        label="Analyze",
        description="Decision-grade analysis brief: market, competition, effort vs value, risks.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=False,
        plugin=BUSINESS_PLUGIN,
    ),
    Capability(
        name="draft-pursuit",
        skill="draft-pursuit",
        label="Draft pursuit",
        description="Corpus-grounded outreach message or proposal for a business opportunity.",
        requires_opportunity=True,
        requires_input=False,
        include_profile=True,
        plugin=BUSINESS_PLUGIN,
    ),
]

REGISTRY: dict[str, Capability] = {c.name: c for c in CAPABILITIES}

# Plugin-qualified names for ClaudeAgentOptions.skills.
SKILL_NAMES = [f"{c.plugin}:{c.skill}" for c in CAPABILITIES]


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


def contacts_block(contacts: list[Contact] | None) -> str:
    if not contacts:
        return "- (no contacts on file — import from Google or add manually)"
    by_org: dict[str, list[str]] = {}
    for c in contacts:
        by_org.setdefault(c.organization or "(unknown organization)", []).append(c.name)
    lines = [f"- {org}: {', '.join(names)}" for org, names in list(by_org.items())[:40]]
    return "\n".join(lines)


def preferences_block(profile: Profile | None) -> str:
    if profile is None:
        return "- (no preferences set — infer from the profile/corpus)"
    lines = []
    if profile.dealbreakers:
        lines.append("- dealbreakers (if the role matches ANY, rate Skip): " + ", ".join(profile.dealbreakers))
    if profile.must_haves:
        lines.append("- must-haves: " + ", ".join(profile.must_haves))
    if profile.nice_to_haves:
        lines.append("- nice-to-haves: " + ", ".join(profile.nice_to_haves))
    return "\n".join(lines) or "- (no preferences set — infer from the profile/corpus)"


def build_prompt(
    cap: Capability,
    *,
    opportunity: Opportunity | None = None,
    input_text: str = "",
    profile: Profile | None = None,
    contacts: list[Contact] | None = None,
) -> str:
    parts = [
        f'Use the "{cap.plugin}:{cap.skill}" skill now (via the Skill tool), '
        "then follow its write-back contract exactly."
    ]
    if opportunity is not None:
        parts.append("Opportunity:\n" + opportunity_block(opportunity))
    if cap.include_profile:
        parts.append("Candidate profile (synthesized):\n" + profile_block(profile))
    if cap.include_preferences:
        parts.append("Job preferences:\n" + preferences_block(profile))
    if cap.include_contacts:
        parts.append("Contacts (grouped by organization):\n" + contacts_block(contacts))
    if input_text.strip():
        parts.append("Input:\n" + input_text.strip())
    return "\n\n".join(parts)
