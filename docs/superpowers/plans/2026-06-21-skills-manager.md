# Skills Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Checkbox steps.

**Goal:** Curated `pinned_skills` on Profile (survive re-synthesis) — model + migration + service + `PATCH /api/corpus/profile` + a curated-skills add/remove UI in the Profile tab.

**Architecture:** Add a JSON `pinned_skills` column (migrated via `_ensure_column`); `synthesize_profile` is untouched so curation persists. Frontend: ProfileTab gains a curated-skills block.

## Global Constraints
- `pinned_skills` is a `list[str]`, deduped/trimmed, NOT touched by `synthesize_profile`.
- Migration: `_ensure_column(engine, "profile", "pinned_skills", "JSON DEFAULT '[]'")` in `init_db` (existing profile rows get `[]`).
- Backend test-first; frontend `npm --prefix frontend run build`. `Profile` already wiped in `tests/conftest.py` `_clear_db`.
- Run `.venv/bin/python -m pytest -q` + `scripts/ci/gate.sh`.

---

### Task 1: Backend — model + migration + service + PATCH endpoint

**Files:** Modify `app/models.py`, `app/db.py`, `app/profile_service.py`, `app/routers/corpus.py`; Test `tests/test_pinned_skills.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pinned_skills.py
from __future__ import annotations

from collections.abc import AsyncIterator

from claude_agent_sdk import AssistantMessage, TextBlock
from sqlmodel import Session, select

from app.db import engine
from app.models import Profile
from app.profile_service import set_pinned_skills, synthesize_profile


def test_set_pinned_skills_creates_then_updates_and_dedupes():
    with Session(engine) as s:
        p = set_pinned_skills(s, ["  Python ", "Python", "MLOps", ""])
        assert p.pinned_skills == ["Python", "MLOps"]  # trimmed, deduped, empties dropped
        p2 = set_pinned_skills(s, ["Leadership"])
        assert p2.id == p.id and p2.pinned_skills == ["Leadership"]


async def test_synthesize_preserves_pinned_skills():
    with Session(engine) as s:
        set_pinned_skills(s, ["Sparkplug B"])
    reply = ('{"headline":"X","summary":null,"skills":["PyTorch"],"experience":[],'
             '"achievements":[],"target_titles":[],"locations":[]}')

    async def fake(*, prompt, options) -> AsyncIterator:
        yield AssistantMessage(content=[TextBlock(text=reply)], model="fake")

    # seed a corpus doc so synthesize doesn't ValueError on empty corpus
    from app.corpus_service import ingest_document
    from app.models import DocumentMediaType, DocumentSource
    with Session(engine) as s:
        ingest_document(s, title="cv.md", source_kind=DocumentSource.paste,
                        media_type=DocumentMediaType.md, data=b"Jane. PyTorch.",
                        embedder=lambda texts: [[1.0, 0.0] for _ in texts])
        await synthesize_profile(s, query_fn=fake)
    with Session(engine) as s:
        row = s.exec(select(Profile)).first()
    assert row.skills == ["PyTorch"] and row.pinned_skills == ["Sparkplug B"]


def test_patch_profile_endpoint(client):
    res = client.patch("/api/corpus/profile", json={"pinned_skills": ["DTDL", "UNS"]})
    assert res.status_code == 200 and res.json()["pinned_skills"] == ["DTDL", "UNS"]
    got = client.get("/api/corpus/profile").json()
    assert got["pinned_skills"] == ["DTDL", "UNS"]
```

- [ ] **Step 2: Run → fail** — `.venv/bin/python -m pytest tests/test_pinned_skills.py -v` (ImportError: set_pinned_skills / no pinned_skills attr).

- [ ] **Step 3a: Model** — in `app/models.py` `Profile`, after `locations`, add:
```python
    pinned_skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))
```

- [ ] **Step 3b: Migration** — in `app/db.py` `init_db`, after the existing `_ensure_column` calls, add:
```python
    _ensure_column(engine, "profile", "pinned_skills", "JSON DEFAULT '[]'")
```

- [ ] **Step 3c: Service** — in `app/profile_service.py` (it imports `Session`, `select`, `Profile`, `_utcnow`), add:
```python
def set_pinned_skills(session: Session, skills: list[str]) -> Profile:
    cleaned: list[str] = []
    for s in skills:
        t = s.strip()
        if t and t not in cleaned:
            cleaned.append(t)
    row = session.exec(select(Profile)).first()
    if row is None:
        row = Profile()
    row.pinned_skills = cleaned
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
```

- [ ] **Step 3d: Endpoint** — in `app/routers/corpus.py`, add `set_pinned_skills` to the `from app.profile_service import ...` line, ensure `from pydantic import BaseModel` is imported (it imports `ValidationError` from pydantic — add `BaseModel`), and add:
```python
class PinnedSkillsUpdate(BaseModel):
    pinned_skills: list[str]


@router.patch("/profile", response_model=Profile)
def update_profile(
    body: PinnedSkillsUpdate, session: Session = Depends(get_session)
) -> Profile:
    return set_pinned_skills(session, body.pinned_skills)
```

- [ ] **Step 4: Run → pass** — `pytest tests/test_pinned_skills.py -v` (3 tests). Then `pytest -q` + `scripts/ci/gate.sh`.

- [ ] **Step 5: Commit** — `git add app/models.py app/db.py app/profile_service.py app/routers/corpus.py tests/test_pinned_skills.py && git commit -m "feat(profile): curated pinned_skills (survive re-synthesis)"`

---

### Task 2: Frontend api.ts

**Files:** Modify `frontend/lib/api.ts`.

- [ ] **Step 1:** Add `pinned_skills: string[];` to the existing `Profile` type (beside `skills`). Append:
```typescript
export async function updatePinnedSkills(skills: string[]): Promise<Profile> {
  const res = await fetch("/api/corpus/profile", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pinned_skills: skills }),
  });
  if (!res.ok) throw new Error(`update skills failed: ${res.status}`);
  return res.json();
}
```
- [ ] **Step 2: Verify** — `npm --prefix frontend run build`.
- [ ] **Step 3: Commit** — `git add frontend/lib/api.ts && git commit -m "feat(ui): Profile.pinned_skills + updatePinnedSkills"`

---

### Task 3: ProfileTab — curated skills add/remove

**Files:** Modify `frontend/app/components/ProfileTab.tsx`.

- [ ] **Step 1:** READ the file. It renders a `ProfileCard` (read-only) including `profile.skills`. Add a **"Your skills"** curated block (works whether or not a profile is synthesized — it reads `profile?.pinned_skills ?? []`). Wire it to `updatePinnedSkills`:
  - State: `const [skillInput, setSkillInput] = useState("")`.
  - Render removable chips for each pinned skill: `× ` button → `updatePinnedSkills(pinned.filter(x => x !== s)).then(setProfile)` (update the local profile state with the returned row).
  - An input + Add button: on submit, `updatePinnedSkills([...pinned, skillInput.trim()]).then((p) => { setProfile(p); setSkillInput(""); })` (guard empty).
  - Keep the existing synthesized `profile.skills` display, relabeled **"Detected skills"** to distinguish from curated.
  - If the component currently only renders the block when `profile` exists, render the curated block even when `profile` is null (use `profile?.pinned_skills ?? []`); the PATCH creates the Profile row, and `setProfile` populates it.
  Match the file's real structure (the `ProfileCard` subcomponent, the `setProfile` setter, the chip styling already used for skills).
- [ ] **Step 2: Verify** — `npm --prefix frontend run build`; `pytest -q`; `scripts/ci/gate.sh`.
- [ ] **Step 3: Commit** — `git add frontend/app/components/ProfileTab.tsx && git commit -m "feat(ui): curated skills manager in Profile tab"`

---

## Final verification
- [ ] `pytest -q` pass; `scripts/ci/gate.sh` PASSED; `npm --prefix frontend run build` OK; 3 commits.

## Self-Review
- Spec coverage: model+migration+service+endpoint (T1), api types (T2), UI (T3). `synthesize_profile` untouched → pinned survive (tested). `set_pinned_skills(session, list[str]) -> Profile` consistent across service/endpoint/test. Migration mirrors the existing `_ensure_column` review_status pattern. No placeholders beyond T3's "read the real ProfileTab structure" instruction.
