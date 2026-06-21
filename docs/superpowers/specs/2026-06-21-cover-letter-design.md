# Design: Cover Letter Capability

**Date:** 2026-06-21
**Status:** Approved (autonomous goal) — feature

## 1. Purpose

Add a one-click **Cover letter** capability: draft a corpus-grounded cover letter
for the selected opportunity, saved as a `cover_letter` artifact. The artifact
kind + pipeline already exist (`cover_letter` is in `GENERATIVE_KINDS` → auto
grounding-check → `needs_review` → approve → export docx/pdf); only the authored
skill + capability entry are missing.

## 2. Scope

A new authored skill `skills/career-pack/skills/cover-letter/SKILL.md` + a
`Capability` registry entry + registry test count bumps (10 → 11). No backend
service, no frontend code (capability bar auto-renders; grounding/export already
handle `cover_letter`). Mirrors `cv-tailor`.

**Out of scope:** input box for a custom angle (uses the opportunity + profile);
multiple length variants. 

## 3. Authored skill — `skills/career-pack/skills/cover-letter/SKILL.md`

Mirror `cv-tailor`'s structure (frontmatter, grounding rules, steps, write-back
contract). Frontmatter `name: cover-letter`. The skill:
- Reads the Opportunity + Candidate profile blocks.
- Runs `mcp__app__search_corpus` (≥3 queries) for the role's key requirements.
- Drafts a focused cover letter (greeting, hook tying the candidate's *real*
  corpus-supported background to the role, 2–3 substantiated value paragraphs,
  close). **Anti-fabrication (MUST):** every claim from the corpus/profile;
  unsupported wants written as `[MISSING: …]`, never invented.
- Calls `mcp__app__save_artifact` with `kind="cover_letter"`,
  `title="Cover letter — <organization> <role>"`, `opportunity_id` from the
  block, `provenance="career-pack:cover-letter"`, `body` = the markdown letter.
- Notes that the backend auto-grounds it to `needs_review` (don't self-approve).

## 4. Capability registry — `app/capabilities.py`

Add after `cv-tailor`:
```python
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
```

## 5. Testing

- `tests/test_capabilities.py`: add `"cover-letter"` to the expected set; bump
  `len(SKILL_NAMES) == 10` → `11`.
- `tests/test_capabilities_api.py`: add to the expected set + bump count.
- `tests/test_career_pack.py`: add to `EXPECTED_SKILLS` + bump count.
- `test_registry_skills_match_pack_directories` passes once both the entry and
  the `cover-letter` directory exist.
- e2e (chat → cover letter artifact → grounded → approve → export) is a live
  agent run, verified manually; not in the offline suite.

Run `.venv/bin/python -m pytest -q` + `scripts/ci/gate.sh`.
