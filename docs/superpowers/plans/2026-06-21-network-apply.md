# Network-Scan + Apply-Prep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add `network-scan` and `apply-prep` career capabilities (adapted from proficiently, attributed), with contacts inlined for network-scan and an ATS reference for apply-prep.

## Global Constraints
- Adapt concepts only — write the skills + reference in this project's own words; do NOT copy proficiently text.
- pytest: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest …`. Verify: `bash scripts/ci/gate.sh` GREEN.
- Do NOT invoke any finishing/branch skill — stop after committing and reporting.

---

### Task 1: Both capabilities + contacts wiring + reference + attribution

**Files:**
- Modify: `app/capabilities.py` (`include_contacts` + `contacts_block` + build_prompt + 2 entries)
- Modify: `app/routers/capabilities.py` (fetch contacts for `include_contacts`)
- Create: `skills/career-pack/skills/network-scan/SKILL.md`, `skills/career-pack/skills/apply-prep/SKILL.md`, `docs/references/ats-patterns.md`
- Modify: `ATTRIBUTION.md`
- Modify (test expectations): `tests/test_career_pack.py`, `tests/test_capabilities.py`, `tests/test_capabilities_api.py`, `tests/test_integration_smoke.py`
- Test: `tests/test_contacts_prompt.py`

- [ ] **Step 1: Update test expectations (red first)**

- `tests/test_career_pack.py`: add `"network-scan"` and `"apply-prep"` to `EXPECTED_SKILLS`; change `== 13` → `== 15`.
- `tests/test_capabilities.py`: change `== 13` → `== 15`; add both names to the hardcoded registry name-set if present.
- `tests/test_capabilities_api.py`: add `"network-scan"`, `"apply-prep"` to the `by_name` set; change `== 13` → `== 15`.
- `tests/test_integration_smoke.py`: change `len(names) == 13` → `== 15`.

- [ ] **Step 2: New prompt test (red)**

Create `tests/test_contacts_prompt.py`:
```python
from sqlmodel import Session

from app.db import engine
from app import capabilities as caps, services
from app.models import Opportunity, OpportunityType


def _cap(name):
    return next(c for c in caps.CAPABILITIES if c.name == name)


def test_network_scan_prompt_inlines_contacts():
    with Session(engine) as s:
        services.add_contact(s, name="Jane Smith", organization="Stripe")
        contacts = services.list_contacts(s)
    prompt = caps.build_prompt(_cap("network-scan"), contacts=contacts)
    assert "Contacts (grouped by organization):" in prompt
    assert "Stripe" in prompt and "Jane Smith" in prompt


def test_apply_prep_prompt_has_opportunity_not_contacts():
    opp = Opportunity(type=OpportunityType.job, title="Role", organization="Co")
    prompt = caps.build_prompt(_cap("apply-prep"), opportunity=opp)
    assert "Opportunity:" in prompt
    assert "Contacts (grouped by organization):" not in prompt
```

- [ ] **Step 3: Run → fail.**

- [ ] **Step 4: Capabilities wiring**

In `app/capabilities.py`:
- Add `include_contacts: bool = False` to the `Capability` dataclass (after `include_preferences`).
- Add a helper:
```python
def contacts_block(contacts: list["Contact"] | None) -> str:
    if not contacts:
        return "- (no contacts on file — import from Google or add manually)"
    by_org: dict[str, list[str]] = {}
    for c in contacts:
        by_org.setdefault(c.organization or "(unknown organization)", []).append(c.name)
    lines = [f"- {org}: {', '.join(names)}" for org, names in list(by_org.items())[:40]]
    return "\n".join(lines)
```
(Import `Contact` in the `TYPE_CHECKING`/models import block as the other models are imported.)
- In `build_prompt`, add a param `contacts: list["Contact"] | None = None`, and after the preferences block append:
```python
    if cap.include_contacts:
        parts.append("Contacts (grouped by organization):\n" + contacts_block(contacts))
```
- Add the two entries to `CAPABILITIES` (after `sms-analyser`):
```python
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
```

- [ ] **Step 5: Router fetches contacts**

In `app/routers/capabilities.py` `invoke`, after the `profile = …` line, add:
```python
    contacts = services.list_contacts(session) if cap.include_contacts else None
```
and pass `contacts=contacts` into the `caps.build_prompt(...)` call. (Import `services` if not already imported.)

- [ ] **Step 6: Create the two skills**

`skills/career-pack/skills/network-scan/SKILL.md`:
```markdown
---
name: network-scan
description: Use when the user wants to scan the companies where they know someone for job openings that match them — surfaces warm-intro opportunities.
---

# Network Scan

Find openings at companies where the user already has a contact, so they can
pursue roles with a warm introduction. Adapted from the proficiently network-scan
process for this project's Contacts + corpus.

## Steps

1. Read the Candidate profile, Job preferences (if present), and **Contacts**
   blocks. The Contacts block lists people grouped by their organization.
2. For each distinct organization that has a contact, use `WebSearch` (and
   `WebFetch` to confirm) to find LIVE current openings at that company that match
   the candidate's target titles and must-haves. Skip organizations with no
   relevant opening. Only keep roles you can source to a real posting URL.
3. For each genuinely matching opening (at most 10 total), call
   `mcp__app__save_opportunity`: `type="job"`, `title`, `organization`, `url`
   (the posting — REQUIRED), `summary` (why it fits AND that the user knows
   <contact name> there), `source="network-scan"`, `dedupe_key` = the URL.
4. For each saved opening, call `mcp__app__record_action`:
   `title="Ask <contact> about <role> at <organization>"`, `kind="outreach"`.
5. Never fabricate a posting, a URL, or a contact. Reply with a ranked,
   one-line-per-find summary naming the contact for each.

## Write-back contract (MUST)

- `mcp__app__save_opportunity` per find — `type="job"`, `url` REQUIRED,
  `source="network-scan"`, `dedupe_key` = the URL. Max 10 per scan.
- `mcp__app__record_action` per find — `kind="outreach"`, naming the contact for
  the warm intro.
```

`skills/career-pack/skills/apply-prep/SKILL.md`:
```markdown
---
name: apply-prep
description: Use when the user is ready to apply to an opportunity — assembles an application kit (what to submit, ATS field guidance, reusable answers). Does not auto-fill forms.
---

# Apply Prep

Assemble everything needed to submit an application for ONE opportunity. This does
NOT fill web forms (no browser automation) — it prepares a kit the user submits.
Adapted from the proficiently apply process; ATS knowledge lives in
`docs/references/ats-patterns.md`.

## Steps

1. Read the Opportunity and Candidate profile blocks, and the Input (an
   application/ATS URL, if the user gave one).
2. Identify the ATS from the URL/posting when possible — Greenhouse, Lever,
   Workday, or other — and recall its field layout + gotchas from
   `docs/references/ats-patterns.md`.
3. Assemble the kit in markdown:
   - **Checklist** — tailored resume + cover letter (if either is missing, say so
     and suggest running `cv-tailor` / `cover-letter` first) plus any
     opportunity-specific items.
   - **ATS** — which system, its key fields, and known gotchas. If you can't tell,
     say so.
   - **Reusable answers** — name, email, phone, LinkedIn, location, work
     authorization, visa sponsorship, EEO (default "Decline to self-identify"),
     filled from the profile/corpus. Mark anything you cannot ground as
     `[MISSING: <field>]`.
4. Call `mcp__app__save_artifact` (contract below).
5. Reply with the ATS, what's ready, and what's still needed.

## Anti-fabrication (non-negotiable)

Use ONLY facts from the profile, corpus, and opportunity. Never invent personal
data (work authorization, addresses, identifiers) — mark gaps `[MISSING: …]`.

## Write-back contract (MUST)

- `mcp__app__save_artifact` — `title="Application kit — <organization> <role>"`,
  `kind="other"`, `opportunity_id` from the Opportunity block,
  `provenance="career-pack:apply-prep"`, `body` = the full kit markdown.
```

- [ ] **Step 7: Create `docs/references/ats-patterns.md`**

Write a SHORT, project-worded reference (your own words) starting with:
`> Adapted from proficientlyjobs/proficiently-claude-skills (MIT). Concepts re-implemented for this project; no text copied.`
Then summarize, as guidance for a human (not browser automation), the three major ATS:
- **Lever** — native form on `jobs.lever.co/{company}/{id}/apply`; easiest; fields: name, email, phone, location, resume upload, links (LinkedIn/GitHub/portfolio), an "Additional information" box (good for a cover letter), EEO survey.
- **Greenhouse** — embedded form (cross-origin iframe) on the posting; fields: first/last name, email, phone, resume + cover-letter uploads, location, "How did you hear about us?", EEO + work-authorization questions.
- **Workday** — multi-step wizard on `*.myworkdayjobs.com`; requires creating an account/sign-in first; pages: My Information, My Experience, Application Questions, Voluntary Disclosures, Self Identify, Review; offers "Autofill with Resume".
Add a one-line difficulty note (Lever easy, Greenhouse medium, Workday hard/needs account).

- [ ] **Step 8: Update `ATTRIBUTION.md`**

Change the "(Later slices) network-scan and an ATS-aware application-prep process."
line to present tense, e.g.:
`- **network-scan** (warm-intro company scan) and **apply-prep** (ATS-aware application kit) — see the career-pack skills and \`docs/references/ats-patterns.md\`.`

- [ ] **Step 9: Run tests + gate**

Run: `… pytest tests/test_contacts_prompt.py tests/test_career_pack.py tests/test_capabilities.py tests/test_capabilities_api.py -q` → PASS
Then `bash scripts/ci/gate.sh` → GATE PASSED.

- [ ] **Step 10: Commit**

```bash
git add app/capabilities.py app/routers/capabilities.py skills/career-pack/skills/network-scan skills/career-pack/skills/apply-prep docs/references/ats-patterns.md ATTRIBUTION.md tests/
git commit -m "feat(career): network-scan + apply-prep capabilities (adapts proficiently, attributed)"
```
