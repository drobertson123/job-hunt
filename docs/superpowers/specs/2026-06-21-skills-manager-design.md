# Design: Skills Manager (curated skills)

**Date:** 2026-06-21
**Status:** Approved (autonomous goal) — feature

## 1. Purpose

The Profile's `skills` are LLM-extracted and **overwritten on every
re-synthesize**, so the user can't curate them. Add a **manager for curated
skills** that the user maintains (add/remove) and that **survive re-synthesis**.
("Resume management" already exists — the corpus tab uploads/lists/deletes resume
documents — so this slice focuses on the missing skills manager.)

## 2. Scope

A new `pinned_skills` list on `Profile` (never touched by synthesis), a
`set_pinned_skills` service, a `PATCH /api/corpus/profile` endpoint, and a
curated-skills add/remove UI in the Profile tab shown alongside the read-only
synthesized skills.

**Out of scope:** editing headline/summary/experience (those remain
synthesis-owned for now); reordering; skill categories.

## 3. Model + migration

- `app/models.py` `Profile` gains:
  `pinned_skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))`.
- `app/db.py` `init_db`: `_ensure_column(engine, "profile", "pinned_skills", "JSON DEFAULT '[]'")`
  (the real `profile` table already has a row; existing rows get `[]`).
- `synthesize_profile` is UNCHANGED — it sets headline/summary/skills/… but
  never `pinned_skills`, so curation is preserved across re-synthesis.

## 4. Service — `app/profile_service.py`

```python
def set_pinned_skills(session: Session, skills: list[str]) -> Profile:
    # get-or-create the single Profile row; set pinned_skills (deduped, trimmed,
    # order preserved, empties dropped); commit; return.
```

## 5. API — `app/routers/corpus.py`

```python
class PinnedSkillsUpdate(BaseModel):
    pinned_skills: list[str]

@router.patch("/profile", response_model=Profile)
def update_profile(body: PinnedSkillsUpdate, session: Session = Depends(get_session)) -> Profile:
    return set_pinned_skills(session, body.pinned_skills)
```
`GET /api/corpus/profile` already returns the `Profile` row (now including
`pinned_skills`).

## 6. Frontend

- `frontend/lib/api.ts`: `Profile` type gains `pinned_skills: string[]`;
  `updatePinnedSkills(skills: string[]): Promise<Profile>` → PATCH.
- `ProfileTab`: a **"Your skills"** (curated) block — removable chips for each
  `pinned_skills` entry (× removes → PATCH the new list → refresh) + an input to
  add one (Enter/Add → append → PATCH). Keep the existing synthesized `skills`
  shown as a separate read-only **"Detected skills"** block. Works even before any
  synthesis (PATCH creates the Profile row if none).

## 7. Testing

Backend TDD: `set_pinned_skills` creates a Profile row when none, updates when
present, dedupes/trims; the existing `synthesize_profile` (stubbed `query_fn`)
does NOT clear `pinned_skills` set beforehand; `PATCH /api/corpus/profile`
returns the row with the new `pinned_skills`; `GET` includes them. Frontend via
`npm --prefix frontend run build`. `profile` is wiped per-test? — confirm/add
`Profile` to `_clear_db` (it's already there from corpus slice).

Run `.venv/bin/python -m pytest -q` + `scripts/ci/gate.sh`.
