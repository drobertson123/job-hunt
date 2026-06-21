# Company Enrichment Capability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `company-enrich` capability: the agent researches the company behind an opportunity and writes the structured `Company` row (linking the opportunity) via `record_company`.

**Architecture:** Extend `upsert_company`/`record_company` with optional opportunity linking (backend, TDD). Add an authored skill `skills/career-pack/skills/company-enrich/SKILL.md` + a `Capability` registry entry; update the registry tests. No frontend change (the capability bar auto-renders from `/api/capabilities`).

**Tech Stack:** Python 3.12, FastAPI, SQLModel, claude-agent-sdk (authored-skill plugins + MCP tools), pytest.

## Global Constraints

- `upsert_company` linking is robust: `link_opportunity_id` sets the opportunity's `company_id` ONLY when the opportunity exists; a missing/None id is a silent no-op (enrichment must not fail on a stale id).
- The skill's anti-fabrication rule: pass only verified fields, omit the rest (incremental upsert leaves omitted fields unchanged); `size` ∈ `startup|smb|mid|large|enterprise|unknown` or omitted.
- Backend test-first; the agent end-to-end run is a live gate, not in the offline suite.
- Run backend tests with `.venv/bin/python -m pytest -q`.
- Adding the capability requires BOTH the registry entry AND the skill directory (the `test_registry_skills_match_pack_directories` test asserts the two sets are equal) — land them together.

---

### Task 1: Backend — `record_company` opportunity linking

**Files:**
- Modify: `app/services.py` (`upsert_company` — add `link_opportunity_id` param + link logic)
- Modify: `app/agent/tools.py` (`record_company` tool — add `link_opportunity_id` arg)
- Test: `tests/test_company_service.py` (add 2), `tests/test_company_tool.py` (add 1)

**Interfaces:**
- Produces: `upsert_company(..., link_opportunity_id: str | None = None)`; `record_company` tool forwards `link_opportunity_id`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_company_service.py`:

```python
def test_upsert_company_links_opportunity():
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role", organization="Acme")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        c = services.upsert_company(s, name="Acme", industry="Energy",
                                    link_opportunity_id=opp.id)
        s.refresh(opp)
        assert opp.company_id == c.id


def test_upsert_company_link_missing_opportunity_is_noop():
    with Session(engine) as s:
        c = services.upsert_company(s, name="Globex", link_opportunity_id="nope")
        assert c.id is not None  # did not raise
```

Add to `tests/test_company_tool.py`:

```python
@pytest.mark.asyncio
async def test_record_company_tool_links_opportunity():
    from app.models import Opportunity, OpportunityType
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        oid = opp.id
    await tools.record_company.handler({"name": "Wayne Ent", "link_opportunity_id": oid})
    with Session(engine) as s:
        linked = s.get(Opportunity, oid)
        assert linked.company_id is not None
```

(`tests/test_company_service.py` already imports `Opportunity`, `OpportunityType`. `tests/test_company_tool.py` imports them inside the new test as shown.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_company_service.py -k link tests/test_company_tool.py -k link -v`
Expected: FAIL — `TypeError: upsert_company() got an unexpected keyword argument 'link_opportunity_id'`.

- [ ] **Step 3: Add the param + link logic to `upsert_company`**

In `app/services.py`, add the parameter to the signature (after `company_id`):

```python
    company_id: str | None = None,
    link_opportunity_id: str | None = None,
) -> Company:
```

And replace the tail (`session.refresh(row)` / `return row`) with:

```python
    session.add(row)
    session.commit()
    session.refresh(row)
    if link_opportunity_id:
        opp = session.get(Opportunity, link_opportunity_id)
        if opp is not None:
            opp.company_id = row.id
            session.add(opp)
            session.commit()
    return row
```

(`Opportunity` is already imported in `app/services.py`.)

- [ ] **Step 4: Add the tool arg in `app/agent/tools.py`**

In the `record_company` tool's args `properties`, after `company_id`, add:

```python
            "link_opportunity_id": {
                "type": "string",
                "description": "set to link this opportunity to the company",
            },
```

And in the `services.upsert_company(...)` call inside `record_company`, add the kwarg (after `company_id=...`):

```python
            company_id=args.get("company_id"),
            link_opportunity_id=args.get("link_opportunity_id"),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_company_service.py tests/test_company_tool.py -v`
Expected: PASS (all company service + tool tests, incl. the 3 new).

- [ ] **Step 6: Commit**

```bash
git add app/services.py app/agent/tools.py tests/test_company_service.py tests/test_company_tool.py
git commit -m "feat(company): record_company can link an opportunity"
```

---

### Task 2: Authored skill + capability registry

**Files:**
- Create: `skills/career-pack/skills/company-enrich/SKILL.md`
- Modify: `app/capabilities.py` (add the `Capability` entry)
- Modify: `tests/test_capabilities.py` (expected set + count)

**Interfaces:**
- Consumes: `record_company` linking (Task 1).
- Produces: the `company-enrich` capability in `CAPABILITIES`/`REGISTRY`/`SKILL_NAMES`.

- [ ] **Step 1: Update the registry tests (failing)**

In `tests/test_capabilities.py`, in `test_registry_has_the_expected_capabilities`, add `"company-enrich"` to the expected set (in the career-pack group):

```python
        "company-research",
        "company-enrich",
        "cv-tailor",
```

And in `test_skill_names_are_plugin_qualified`, change:

```python
    assert len(caps.SKILL_NAMES) == 10
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_capabilities.py -v`
Expected: FAIL — `company-enrich` not in `REGISTRY`; `SKILL_NAMES` length 9 ≠ 10; and `test_registry_skills_match_pack_directories` fails (sets differ).

- [ ] **Step 3: Create the skill**

Create `skills/career-pack/skills/company-enrich/SKILL.md`:

```markdown
---
name: company-enrich
description: Use to research the company behind an opportunity and fill its structured profile (industry, size, ATS vendor, careers URL) — writes the Company row and links the opportunity.
---

# Company Enrich

Research the organization behind an opportunity and write its **structured**
company profile (not a prose brief). Use web search. Pass ONLY fields you
verified from a source — never invent a size, ATS vendor, careers URL, or
domain. Omit anything you cannot verify; omitted fields are left unchanged.

## Steps

1. Identify the organization and the opportunity `id` from the prompt's
   "Opportunity" block.
2. Use `WebSearch` (and `WebFetch` on promising pages) to find, where verifiable:
   `industry`, company `size`, `hq_location`, `ats_vendor`
   (e.g. Greenhouse, Lever, Workday, Ashby), `careers_url`, `domain`, and a
   one-line `summary`.
3. Call `mcp__app__record_company` (write-back contract below) with the verified
   fields and `link_opportunity_id` = the opportunity `id`.
4. Reply with 2–3 bullets: what you filled and what you could not verify.

## Constraints (MUST)

- `size` must be exactly one of: `startup`, `smb`, `mid`, `large`,
  `enterprise`, `unknown`. Map your research to the closest, or omit `size`.
- Never pass a guessed value. If a field is not supported by a source, omit it.

## Write-back contract (MUST)

- `mcp__app__record_company` with: `name` = the organization (verbatim from the
  Opportunity block's `organization`), `link_opportunity_id` = the opportunity
  `id`, plus each verified field (`industry`, `size`, `hq_location`,
  `ats_vendor`, `careers_url`, `domain`, `summary`).
```

- [ ] **Step 4: Add the capability entry**

In `app/capabilities.py`, add to the `CAPABILITIES` list, immediately after the `company-research` entry:

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

- [ ] **Step 5: Run the capability tests, then full suite + gate**

Run: `.venv/bin/python -m pytest tests/test_capabilities.py -v`
Expected: PASS (expected-set includes company-enrich; `SKILL_NAMES` == 10; skills-match-dirs passes since both the entry and the dir now exist).
Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all).
Run: `scripts/ci/gate.sh`
Expected: GATE PASSED.

- [ ] **Step 6: Commit**

```bash
git add skills/career-pack/skills/company-enrich/SKILL.md app/capabilities.py tests/test_capabilities.py
git commit -m "feat(capability): company-enrich (research -> structured Company)"
```

---

## Final verification

- [ ] `.venv/bin/python -m pytest -q` → all pass.
- [ ] `scripts/ci/gate.sh` → GATE PASSED.
- [ ] `git log --oneline` shows 2 focused commits on `feature/company-enrich`.
- [ ] (Manual, post-merge) Run the "Enrich company" capability against a real opportunity and confirm a structured Company is created and linked (Detail tab shows it). Live agent run — not part of the offline suite.

## Self-Review (completed by plan author)

- **Spec coverage:** `upsert_company` link param + no-op-on-missing + tool arg (T1, spec §3); skill SKILL.md with anti-fabrication + write-back contract + capability entry + registry test updates (T2, §4–6); no frontend change (auto-render, §5); live e2e is manual (§6).
- **Placeholder scan:** none — full code/markdown in every step.
- **Type consistency:** `link_opportunity_id: str | None` matches `Opportunity.id: str` and the tool's string arg. The skill calls `mcp__app__record_company` (the qualified tool name). `size` enum values match the model + the tool's `_enum(..., unknown)` guard. Registry test count 9→10 matches adding exactly one capability; `test_registry_skills_match_pack_directories` stays green because the entry's `skill="company-enrich"` equals the new directory name.
