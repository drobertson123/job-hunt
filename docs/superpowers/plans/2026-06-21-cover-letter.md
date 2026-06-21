# Cover Letter Capability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax.

**Goal:** A `cover-letter` capability — authored skill + registry entry; no backend/frontend code.

**Architecture:** Mirror `cv-tailor`. The `cover_letter` artifact kind + grounding/export already exist.

## Global Constraints
- New skill at `skills/career-pack/skills/cover-letter/SKILL.md` AND a `Capability` entry must land together (the `test_registry_skills_match_pack_directories` test asserts the set of career-pack capability skills == the directory names).
- `REGISTRY`/`SKILL_NAMES` derive from `CAPABILITIES`. Backend test-first for the registry; the skill itself is prose.
- Run `.venv/bin/python -m pytest -q` + `scripts/ci/gate.sh`.

---

### Task 1: Skill + capability + registry tests

**Files:** Create `skills/career-pack/skills/cover-letter/SKILL.md`; Modify `app/capabilities.py`, `tests/test_capabilities.py`, `tests/test_capabilities_api.py`, `tests/test_career_pack.py`.

- [ ] **Step 1: Update the registry tests (failing first)**

In `tests/test_capabilities.py` (`test_registry_has_the_expected_capabilities`) add `"cover-letter"` to the career-pack group of the expected set; and in `test_skill_names_are_plugin_qualified` change `len(caps.SKILL_NAMES) == 10` → `== 11`.
In `tests/test_capabilities_api.py`: add `"cover-letter"` to its expected set and bump its count 10 → 11.
In `tests/test_career_pack.py`: add `"cover-letter"` to `EXPECTED_SKILLS` and bump its count 10 → 11.
(Read each test first to match the exact assertion shape — the company-enrich slice did the identical 9→10 bump across these same three files.)

- [ ] **Step 2: Run → fail** — `.venv/bin/python -m pytest tests/test_capabilities.py tests/test_capabilities_api.py tests/test_career_pack.py -v` (cover-letter not in REGISTRY / count mismatch / dir mismatch).

- [ ] **Step 3: Create the skill** — `skills/career-pack/skills/cover-letter/SKILL.md`:

```markdown
---
name: cover-letter
description: Use when the user asks for a cover letter for an opportunity — produces a corpus-grounded cover-letter artifact, never inventing experience.
---

# Cover Letter (corpus-grounded)

Write a cover letter for ONE opportunity, grounded EXCLUSIVELY in the user's
corpus and profile. This document asserts facts about the user — fabrication is
the one unforgivable failure.

## Grounding rules (non-negotiable)

- Before writing, call `mcp__app__search_corpus` for the role's key requirements
  (skills, domain, leadership, tooling) — at least 3 queries.
- Every claim, employer, metric, and skill MUST come from a corpus passage or the
  Candidate profile block. If the posting wants something you cannot find, write
  `[MISSING: <the thing>]` instead of inventing it.
- Never inflate titles, dates, or numbers. Reword freely; never add facts.

## Steps

1. Read the Opportunity and Candidate profile blocks.
2. Run the corpus searches (grounding rules above).
3. Draft the letter in markdown: a greeting; an opening hook tying the
   candidate's strongest corpus-supported background to this role; 2–3
   paragraphs each substantiating a value claim with a supported example; a
   concise close. Keep it under ~400 words and specific to this opportunity.
4. Call `mcp__app__save_artifact` (write-back contract below).
5. Reply with the angle you took and list any `[MISSING: …]` gaps.

## Write-back contract (MUST)

- `mcp__app__save_artifact` with: `title="Cover letter — <organization> <role>"`,
  `kind="cover_letter"`, `opportunity_id` from the Opportunity block,
  `provenance="career-pack:cover-letter"`, `body` = the full markdown letter.

The backend automatically grounds this artifact; it lands as `needs_review`.
That is expected — do not try to approve it.
```

- [ ] **Step 4: Add the capability entry** — in `app/capabilities.py`, after the `cv-tailor` entry:

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

- [ ] **Step 5: Run tests + suite + gate** — `pytest tests/test_capabilities.py tests/test_capabilities_api.py tests/test_career_pack.py -v` (pass); `pytest -q` (all); `scripts/ci/gate.sh` (PASSED).

- [ ] **Step 6: Commit** — `git add skills/career-pack/skills/cover-letter/SKILL.md app/capabilities.py tests/test_capabilities.py tests/test_capabilities_api.py tests/test_career_pack.py && git commit -m "feat(capability): cover-letter (corpus-grounded cover letter)"`

---

## Final verification
- [ ] `pytest -q` pass; `scripts/ci/gate.sh` PASSED; 1 commit on `feature/cover-letter`.

## Self-Review
- Spec coverage: skill + capability + 3 test files bumped (T1). Mirrors cv-tailor/company-enrich. `cover_letter` already in GENERATIVE_KINDS. Skill↔registry↔dir names align (`cover-letter`). No placeholders.
