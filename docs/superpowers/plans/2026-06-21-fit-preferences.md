# Job Preferences + Fit-Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add job preferences (dealbreakers/must-haves/nice-to-haves) to Profile and rewrite fit-analysis to use the decisive rubric; attribute the proficiently source.

**Architecture:** Three JSON-list fields on the existing `Profile`; `set_preferences` service; extended `PATCH /api/corpus/profile`; a `preferences_block` inlined into fit-analysis prompts; rewritten fit-analysis SKILL.md; attribution + references docs; ProfileTab UI.

## Global Constraints
- Adapt CONCEPTS only — do NOT copy text from the proficiently repo. Add the attribution header (see spec) to the references and ATTRIBUTION.md.
- `synthesize_profile` must NOT touch the new preference fields (user-curated).
- pytest: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest …`. Frontend: `npm --prefix frontend install` then build. Verify: `bash scripts/ci/gate.sh` GREEN + frontend build.
- Do NOT invoke any finishing/branch skill — stop after committing and reporting.

---

### Task 1: Profile preference fields + service + PATCH

**Files:**
- Modify: `app/models.py` (3 fields), `app/db.py` (3 `_ensure_column`)
- Modify: `app/profile_service.py` (`set_preferences`)
- Modify: `app/routers/corpus.py` (extend the profile PATCH)
- Test: `tests/test_preferences.py`

- [ ] **Step 1: Model fields + migration**

In `app/models.py` `class Profile`, after `pinned_skills: ...`, add:
```python
    dealbreakers: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    must_haves: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    nice_to_haves: list[str] = Field(default_factory=list, sa_column=Column(JSON))
```
In `app/db.py` `init_db`, after the existing `_ensure_column(...)` lines:
```python
    _ensure_column(engine, "profile", "dealbreakers", "JSON DEFAULT '[]'")
    _ensure_column(engine, "profile", "must_haves", "JSON DEFAULT '[]'")
    _ensure_column(engine, "profile", "nice_to_haves", "JSON DEFAULT '[]'")
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_preferences.py`:
```python
from sqlmodel import Session

from app.db import engine
from app import profile_service as ps
from app.models import Profile


def test_set_preferences_partial_and_clean():
    with Session(engine) as s:
        row = ps.set_preferences(s, dealbreakers=[" agency ", "crypto", "agency"], must_haves=["remote"])
        assert row.dealbreakers == ["agency", "crypto"]  # trimmed + deduped
        assert row.must_haves == ["remote"]
        assert row.nice_to_haves == []
        # partial update leaves the untouched field intact
        row2 = ps.set_preferences(s, nice_to_haves=["equity"])
        assert row2.dealbreakers == ["agency", "crypto"] and row2.nice_to_haves == ["equity"]


def test_synthesize_profile_does_not_touch_preferences():
    async def fake_query(*a, **k):
        from claude_agent_sdk import AssistantMessage, TextBlock
        yield AssistantMessage(content=[TextBlock(text='{"headline":"H","summary":"S","skills":[],"target_titles":[],"locations":[]}')], model="m")

    import asyncio
    with Session(engine) as s:
        ps.set_preferences(s, dealbreakers=["agency"])
    asyncio.get_event_loop().run_until_complete(_synth(fake_query))
    with Session(engine) as s:
        assert s.exec(__import__("sqlmodel").select(Profile)).first().dealbreakers == ["agency"]


async def _synth(fake_query):
    from sqlmodel import Session as S
    from app import profile_service as ps
    with S(engine) as s:
        await ps.synthesize_profile(s, corpus_text="x", query_fn=fake_query)


def test_patch_profile_sets_preferences(client):
    r = client.patch("/api/corpus/profile", json={
        "dealbreakers": ["on-site only"], "must_haves": ["staff+"], "nice_to_haves": ["AI"],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["dealbreakers"] == ["on-site only"]
    assert body["must_haves"] == ["staff+"] and body["nice_to_haves"] == ["AI"]
```
(If `synthesize_profile`'s signature differs, adjust `_synth` to match its real params — read `app/profile_service.py` first. The key assertion is that preferences survive synthesis.)

- [ ] **Step 3: Run → fail.**

- [ ] **Step 4: Implement `set_preferences` + extend the PATCH**

In `app/profile_service.py`, add (mirroring `set_pinned_skills`):
```python
def _clean_list(items: list[str]) -> list[str]:
    out: list[str] = []
    for s in items or []:
        t = s.strip()
        if t and t not in out:
            out.append(t)
    return out


def set_preferences(
    session: Session,
    *,
    dealbreakers: list[str] | None = None,
    must_haves: list[str] | None = None,
    nice_to_haves: list[str] | None = None,
) -> Profile:
    row = session.exec(select(Profile)).first()
    if row is None:
        row = Profile()
    if dealbreakers is not None:
        row.dealbreakers = _clean_list(dealbreakers)
    if must_haves is not None:
        row.must_haves = _clean_list(must_haves)
    if nice_to_haves is not None:
        row.nice_to_haves = _clean_list(nice_to_haves)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
```
(Reuse the existing `select`/`Session`/`Profile` imports.)

In `app/routers/corpus.py`, extend the profile-PATCH request model (the one with `pinned_skills`) to also accept `dealbreakers`/`must_haves`/`nice_to_haves` (all `list[str] | None = None`), and in the handler call `profile_service.set_pinned_skills(...)` when `pinned_skills is not None` AND `profile_service.set_preferences(...)` with whichever preference lists are not None; return the resulting Profile. Read the current handler and keep its existing behavior.

- [ ] **Step 5: Run the test + gate** → PASS / GATE PASSED.

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/db.py app/profile_service.py app/routers/corpus.py tests/test_preferences.py
git commit -m "feat(preferences): dealbreakers/must-haves/nice-to-haves on Profile + PATCH"
```

---

### Task 2: Fit rubric rewrite + prompt wiring + attribution

**Files:**
- Modify: `app/capabilities.py` (`include_preferences` + `preferences_block` + build_prompt)
- Modify: `skills/career-pack/skills/fit-analysis/SKILL.md` (rubric)
- Create: `ATTRIBUTION.md`, `docs/references/fit-scoring.md`, `docs/references/priority-hierarchy.md`
- Test: `tests/test_preferences_prompt.py`

- [ ] **Step 1: Capability flag + block + build_prompt**

In `app/capabilities.py`:
- Add `include_preferences: bool = False` to the `Capability` dataclass (after `include_profile`). (Default keeps every existing entry valid.)
- Set `include_preferences=True` on the `fit-analysis` Capability entry.
- Add a `preferences_block(profile)` helper:
```python
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
```
- In `build_prompt`, after the profile block append, add:
```python
    if cap.include_preferences:
        parts.append("Job preferences:\n" + preferences_block(profile))
```

- [ ] **Step 2: Failing prompt test**

Create `tests/test_preferences_prompt.py`:
```python
from sqlmodel import Session

from app.db import engine
from app import capabilities as caps, profile_service as ps
from app.models import Opportunity, OpportunityType


def _cap(name):
    return next(c for c in caps.CAPABILITIES if c.name == name)


def test_fit_analysis_prompt_includes_preferences():
    with Session(engine) as s:
        profile = ps.set_preferences(s, dealbreakers=["on-site only"], must_haves=["staff+"])
    opp = Opportunity(type=OpportunityType.job, title="Role", organization="Co")
    prompt = caps.build_prompt(_cap("fit-analysis"), opportunity=opp, profile=profile)
    assert "Job preferences:" in prompt
    assert "on-site only" in prompt and "staff+" in prompt


def test_cover_letter_prompt_omits_preferences():
    opp = Opportunity(type=OpportunityType.job, title="Role", organization="Co")
    prompt = caps.build_prompt(_cap("cover-letter"), opportunity=opp, profile=None)
    assert "Job preferences:" not in prompt
```

- [ ] **Step 3: Run → fail; then implement (Step 1 already covers it) → pass.**

- [ ] **Step 4: Rewrite `skills/career-pack/skills/fit-analysis/SKILL.md`**

Keep the frontmatter `name: fit-analysis` and description. Insert a new rubric step BEFORE the dimension scoring, and have the verdict/decision lead with the rating word. The new Steps section:
```markdown
## Steps

1. Read the Opportunity, Candidate profile, and **Job preferences** blocks. If the
   profile block is empty, call `mcp__app__search_corpus` for the role's main
   requirements.
2. **Apply the preferences rubric first (decisive):**
   - **Dealbreakers** — if the opportunity matches ANY dealbreaker, the rating is
     **Skip**. Name the dealbreaker(s) and do not bother scoring dimensions.
   - **Must-haves** — count how many are met. Few met → likely **Low**.
   - **Nice-to-haves** — for opportunities that clear the must-haves.
   - **Rating:** **High** = no dealbreakers + all must-haves + ≥2 nice-to-haves;
     **Medium** = no dealbreakers + most must-haves (or all must-haves, few
     nice-to-haves); **Low** = no dealbreakers but significant must-have gaps;
     **Skip** = any dealbreaker. If no preferences are set, infer reasonable ones
     from the profile/corpus and say so.
3. Score each dimension 1-5 with one sentence of corpus/profile-grounded evidence:
   skills match, seniority match, domain match, location/logistics, growth.
4. Compute overall = mean of the dimensions, one decimal.
5. Write the analysis in markdown: the **Rating** (High/Medium/Low/Skip) and why,
   the score table, `## Strengths`, `## Gaps & risks`, `## Verdict`
   (pursue / deprioritize / pass — must agree with the rating).
6. Call `mcp__app__save_artifact` then `mcp__app__record_decision` (contract below).
7. Reply with the rating, the overall score, and the verdict sentence.
```
Keep the existing `## Write-back contract` section, but change the
`record_decision` `summary` to lead with the rating:
`summary="<Rating> · Fit <overall>/5 — <verdict word>: <role title> @ <organization>"`.

- [ ] **Step 5: Attribution + references**

Create `ATTRIBUTION.md`:
```markdown
# Attribution

Parts of this project's job-hunt **work processes** are adaptations of concepts
from **[proficientlyjobs/proficiently-claude-skills](https://github.com/proficientlyjobs/proficiently-claude-skills)** (MIT License), by Proficiently.

We re-implemented the *concepts* against this project's own architecture (SQLite
system-of-record, in-process MCP write-back tools, corpus grounding) and local
storage — **no source text was copied**. Adapted concepts include:

- The **fit-scoring rubric** (dealbreakers → must-haves → nice-to-haves →
  High/Medium/Low/Skip) — see `skills/career-pack/skills/fit-analysis/SKILL.md`
  and `docs/references/fit-scoring.md`.
- The **job-preferences** model (dealbreakers / must-haves / nice-to-haves),
  stored on the `Profile` row rather than a `preferences.md` file.
- The **instruction priority hierarchy** — see `docs/references/priority-hierarchy.md`.
- (Later slices) network-scan and an ATS-aware application-prep process.

Original project: https://github.com/proficientlyjobs/proficiently-claude-skills ·
Proficiently: https://proficiently.com
```
Create `docs/references/fit-scoring.md` and `docs/references/priority-hierarchy.md`
— short, project-worded summaries of the rubric and the priority order, EACH
starting with a one-line attribution note:
`> Adapted from proficientlyjobs/proficiently-claude-skills (MIT). Concepts re-implemented for this project; no text copied.`
(Write them in your own words — fit-scoring: the dealbreakers/must/nice rubric +
how it maps to pipeline triage; priority-hierarchy: Accuracy > user corrections >
workflow > writing quality > format > tone, framed around this project's
anti-fabrication rule.)

- [ ] **Step 6: Run the prompt test + career-pack static tests + gate**

Run: `… pytest tests/test_preferences_prompt.py tests/test_career_pack.py -q` → PASS
Then `bash scripts/ci/gate.sh` → GATE PASSED.

- [ ] **Step 7: Commit**

```bash
git add app/capabilities.py skills/career-pack/skills/fit-analysis/SKILL.md ATTRIBUTION.md docs/references/ tests/test_preferences_prompt.py
git commit -m "feat(fit): decisive preferences rubric in fit-analysis + attribution (adapts proficiently)"
```

---

### Task 3: Preferences UI in ProfileTab

**Files:**
- Modify: `frontend/lib/api.ts` (Profile type + updatePreferences)
- Modify: `frontend/app/components/ProfileTab.tsx` (three editable list sections)

- [ ] **Step 1: api.ts**

Add `dealbreakers: string[]`, `must_haves: string[]`, `nice_to_haves: string[]` to the `Profile` type. Add:
```ts
export async function updatePreferences(body: {
  dealbreakers?: string[];
  must_haves?: string[];
  nice_to_haves?: string[];
}): Promise<Profile> {
  const res = await fetch("/api/corpus/profile", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`update preferences failed: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: ProfileTab three editable sections**

Read `frontend/app/components/ProfileTab.tsx` and find the existing pinned-skills editor (removable chips + add input calling `updatePinnedSkills`). Add a **Preferences** area with three chip-list editors — **Dealbreakers**, **Must-haves**, **Nice-to-haves** — each mirroring the pinned-skills pattern but calling `updatePreferences({ dealbreakers })` etc. (add a chip, remove a chip, `.then(setProfile)`). Use the TwinForge tokens already in the file. Label the dealbreakers section so it reads as "any of these → Skip".

- [ ] **Step 3: Build**

Run: `npm --prefix frontend install` then `npm --prefix frontend run build` → succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts frontend/app/components/ProfileTab.tsx
git commit -m "feat(preferences): edit dealbreakers/must-haves/nice-to-haves in Profile tab"
```
