# Design: Company Enrichment Capability

**Date:** 2026-06-20
**Status:** Approved design — ready for implementation plan
**Builds on:** company normalization (`record_company` tool, `Company` model),
the authored-skill/capability architecture (career-pack), and the Detail tab.

## 1. Purpose

Turn a bare `Company` (just a name) into a rich structured profile — industry,
size, HQ, ATS vendor, careers URL, domain — by researching the company behind an
opportunity, and link the opportunity to it. A new `company-enrich` capability:
the agent web-searches, then writes the structured `Company` row via the
`record_company` tool (distinct from the existing `company-research` skill, which
writes an unstructured prose research-brief artifact).

## 2. Scope

Backend: extend `record_company`/`upsert_company` to optionally link an
opportunity. New authored skill `skills/career-pack/skills/company-enrich/` + a
capability registry entry + capability test updates. No frontend change (the
capability bar auto-renders from `/api/capabilities`).

**Out of scope:** enriching all companies in one sweep (one opportunity at a
time, like other capabilities); a combined research-brief + structured-enrich
skill; domain-based company dedup. Follows existing patterns
(`company-research`/`enrich-opportunity` skills, the `Capability` registry).

## 3. Backend — `record_company` gains opportunity linking

`services.upsert_company(...)` gains a parameter:

```python
def upsert_company(session, *, name, ..., company_id=None,
                   link_opportunity_id: str | None = None) -> Company:
```

After the company row is upserted (existing incremental logic), if
`link_opportunity_id` is set and that opportunity exists, set
`opp.company_id = row.id` and commit. No-op when `link_opportunity_id` is None or
the opportunity is missing (don't raise — enrichment shouldn't fail on a stale
id).

`record_company` tool (`app/agent/tools.py`) gains a `link_opportunity_id`
string property in its args schema, forwarded to the service.

## 4. Authored skill — `skills/career-pack/skills/company-enrich/SKILL.md`

Mirrors `company-research`'s structure. Frontmatter `name: company-enrich`,
description for "research a company's structured profile". Steps:

1. Identify the organization and the opportunity `id` from the prompt's
   "Opportunity" block.
2. `WebSearch` (and `WebFetch` on promising pages) to find: `industry`, company
   `size`, `hq_location`, `ats_vendor` (Greenhouse/Lever/Workday/Ashby/…),
   `careers_url`, `domain`, and a one-line `summary`.
3. Call `mcp__app__record_company` (write-back contract below).
4. Reply with a 2–3 bullet summary of what was filled and what couldn't be
   verified.

**Anti-fabrication (MUST):** pass ONLY fields you verified from a source; OMIT
any field you couldn't verify (the incremental upsert leaves omitted fields
unchanged — never send a guessed value). `size` must be exactly one of
`startup | smb | mid | large | enterprise | unknown`; map the research to the
closest, or omit it. Never invent an ATS vendor, careers URL, or domain.

**Write-back contract (MUST):** `mcp__app__record_company` with `name=<the
organization>`, the verified fields, `link_opportunity_id` = the opportunity
`id` from the Opportunity block. (Linking is what surfaces the company in the
Detail tab.)

## 5. Capability registry — `app/capabilities.py`

Add to `CAPABILITIES`:

```python
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
```

`REGISTRY` and `SKILL_NAMES` derive from `CAPABILITIES` automatically. The
frontend capability bar renders the new "Enrich company" button from
`/api/capabilities` with no code change.

## 6. Testing

- **Backend TDD** (`tests/test_company_service.py` extend; `tests/test_company_tool.py` extend):
  `upsert_company(link_opportunity_id=<opp>)` sets that opportunity's
  `company_id`; no-op when the id is None or unknown; the `record_company` tool
  forwards `link_opportunity_id`.
- **Capability registry** (`tests/test_capabilities.py` update): add
  `"company-enrich"` to the expected set in
  `test_registry_has_the_expected_capabilities`; bump `len(SKILL_NAMES) == 9`
  to `== 10`. `test_registry_skills_match_pack_directories` passes automatically
  once both the registry entry and the `company-enrich` skill directory exist
  (it asserts the two sets are equal).
- **End-to-end** (WebSearch → `record_company` → linked Company) is a **live
  agent run**, verified manually against a real opportunity — not in the default
  offline suite, consistent with the other career-pack capabilities (their live
  gates are `OH_RUN_LIVE_PROBE`-gated).

## 7. Notes

- The skill is prose (SKILL.md); the testable surface is the backend linking +
  the registry wiring. The agent behavior is validated by the live run.
- `link_opportunity_id` not raising on a missing opp keeps enrichment robust if
  an opportunity was archived/deleted between prompt build and tool call.
- `size` enum mismatch is guarded at the tool layer (`_enum(..., unknown)`); the
  skill is additionally instructed to send only valid values or omit.
