# Email Analyser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `email-analyser` career-pack capability: paste an email about an opportunity → agent logs an inbound Communication + any follow-up Action via existing MCP write-back tools.

**Architecture:** A new authored skill `skills/career-pack/skills/email-analyser/SKILL.md` plus a `Capability` registry entry. No new backend tools (reuses `record_communication`, `record_action`). Not generative → no grounding/approval.

**Tech Stack:** Python 3.12, the authored career-pack plugin, the capability registry, pytest.

## Global Constraints
- The capability `name` and `skill` are both `"email-analyser"` (must equal the skill directory name — the registry test asserts dir-set == capability-skill-set).
- `requires_opportunity=True`, `requires_input=True`, `include_profile=False`, `plugin=CAREER_PLUGIN`.
- The SKILL.md MUST contain a `## Write-back contract` section and reference `mcp__app__` tools (a static test asserts both).
- No new backend behavior. Verification: `bash scripts/ci/gate.sh` GREEN. pytest interpreter: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest …` (worktree has no local .venv).
- Do NOT invoke any finishing/branch skill — stop after committing and reporting.

---

### Task 1: Add the `email-analyser` capability, skill, and update expectations

**Files:**
- Create: `skills/career-pack/skills/email-analyser/SKILL.md`
- Modify: `app/capabilities.py` (add the Capability entry)
- Modify: `tests/test_career_pack.py` (EXPECTED_SKILLS + count)
- Modify: `tests/test_capabilities.py` (count)
- Modify: `tests/test_capabilities_api.py` (by_name set + count)

**Interfaces:**
- Produces: a `Capability(name="email-analyser", skill="email-analyser", …)` discoverable in `caps.CAPABILITIES`, `caps.SKILL_NAMES`, and the `/api/capabilities` listing.

- [ ] **Step 1: Update the test expectations (these now fail)**

In `tests/test_career_pack.py`, add `"email-analyser"` to the `EXPECTED_SKILLS` set (after `"fit-analysis",`), and change `assert len(opts.skills) == 11` to `== 12`.

In `tests/test_capabilities.py`, change `assert len(caps.SKILL_NAMES) == 11` to `== 12`.

In `tests/test_capabilities_api.py`, add `"email-analyser",` to the `set(by_name) == { … }` literal (in the career block, e.g. after `"fit-analysis",`), and change `assert len(names) == 11` to `== 12`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_career_pack.py tests/test_capabilities.py tests/test_capabilities_api.py -q`
Expected: FAIL (EXPECTED_SKILLS mismatch / count / set mismatch — the capability & skill don't exist yet).

- [ ] **Step 3: Create the skill `SKILL.md`**

Create `skills/career-pack/skills/email-analyser/SKILL.md` with EXACTLY this content:

```markdown
---
name: email-analyser
description: Use when the user pastes an email about an opportunity — extract its meaning and log it as a communication plus any follow-up, never inventing details.
---

# Email Analyser

Analyse ONE pasted email that relates to the given Opportunity, then record what
it means in the tracker. You log facts about a real message — never invent a
date, name, or commitment that is not in the email.

## What to extract

Read the Input (the raw email) and the Opportunity block. Determine:
- **direction**: `inbound` if the user received it, `outbound` if they sent it
  (default `inbound` — analysing a received email is the common case).
- **intent**: interview invite, scheduling, request for info/documents,
  rejection, offer, or general update.
- **subject**: the email's subject line (or a short one you derive if absent).
- **occurred_at**: the email's date/time if shown, as ISO 8601; omit if unknown.
- **key dates / asks**: any interview date/time, deadline, or action the user
  must take — quote them verbatim, do not normalise or guess.

## Anti-fabrication rules (non-negotiable)

- Use ONLY facts present in the email. If a date or detail is not stated, leave
  it out — never infer a follow-up date the email does not give.
- The `body` you store is a concise faithful summary plus any verbatim key lines
  (dates, names, requests). Do not embellish.

## Steps

1. Read the Opportunity block (note its `id`) and the Input email.
2. Call `mcp__app__record_communication` to log the message (contract below).
3. If the email requires the user to do something (reply, schedule, send
   documents, prepare, decide), call `mcp__app__record_action` for that next
   step. If it requires nothing (e.g. a plain rejection or FYI), do not invent
   an action — say so in your reply.
4. Reply with a 2–3 line summary: the intent, what you logged, and any date the
   user must act on.

## Write-back contract

- `mcp__app__record_communication` — required `direction` (`inbound`/`outbound`)
  and `channel` (use `email`); pass `opportunity_id` (the Opportunity `id`),
  `subject`, `body` (your faithful summary), `occurred_at` (ISO 8601, if known),
  `thread_key` (stable per email thread, e.g. the normalised subject), and
  `follow_up_due_at` (ISO 8601) ONLY when the email states or clearly implies a
  reply-by date.
- `mcp__app__record_action` — only when a next step is needed: `title`
  (imperative, e.g. "Reply to recruiter with availability"), `opportunity_id`,
  `kind` (`followup`/`prep`/`outreach`/`apply`/`decision`), `detail` (include any
  interview date/time verbatim from the email), and `due_at` (ISO 8601) only if a
  date is given.
```

- [ ] **Step 4: Add the capability entry**

In `app/capabilities.py`, add this entry to the `CAPABILITIES` list, immediately after the `interview-prep` entry (the closing `),` of that `Capability(...)`):

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest tests/test_career_pack.py tests/test_capabilities.py tests/test_capabilities_api.py -q`
Expected: PASS.

- [ ] **Step 6: Run the full gate**

Run: `bash scripts/ci/gate.sh`
Expected: GATE PASSED (all backend tests green).

- [ ] **Step 7: Commit**

```bash
git add skills/career-pack/skills/email-analyser/SKILL.md app/capabilities.py tests/test_career_pack.py tests/test_capabilities.py tests/test_capabilities_api.py
git commit -m "feat(career): email-analyser capability (email -> communication + follow-up)"
```
