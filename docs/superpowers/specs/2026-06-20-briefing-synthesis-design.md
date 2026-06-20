# Design: Briefing Synthesis (full vertical slice)

**Date:** 2026-06-20
**Status:** Approved design — ready for implementation plan
**Builds on:** the `Briefing` model + `BriefingFactKey` enum (added 2026-06-20) and the `profile_service` synthesis pattern.

## 1. Purpose

Generate a structured quick-reference ("briefing") for an opportunity: answers
to the fixed expected questions (salary range, remote policy, tech stack,
why-fit, concerns, …) plus a short summary, grounded in what's known about the
role/company and the user's own corpus. Surfaced in the UI and synthesizable by
the agent. First use of the `Briefing` model.

## 2. Scope

Full vertical slice: synthesis service → agent write-back tool → API
(synthesize + get + detail include) → frontend Briefing tab. Backend is
test-first with the LLM stubbed.

**Out of scope:** surfacing `source_hash` staleness in the UI; web research for
facts; a per-opportunity detail page; an approval gate (briefings are internal
reference, never sent to employers). Follows existing patterns
(`profile_service`, `record_action`/`record_application` tools, `actions.py`/
opportunity-detail routers, canvas-tab wiring).

## 3. Service — `app/briefing_service.py`

Mirror `app/profile_service.py`: single-turn, tool-less local Claude CLI session
(Agent SDK, CLI auth — no API key), JSON validated by Pydantic, injectable
`query_fn` for tests.

```python
class FactSchema(BaseModel):
    key: BriefingFactKey
    question: str
    answer: str
    confidence: float | None = None
    source: str | None = None

class BriefingSchema(BaseModel):
    summary: str = ""
    facts: list[FactSchema] = Field(default_factory=list)

async def synthesize_briefing(
    session: Session, *, opportunity_id: str,
    query_fn: Callable[..., AsyncIterator[Any]] = sdk_query,
) -> Briefing: ...
```

Behavior:
- Load the `Opportunity` (raise `ValueError` if missing). Load the linked
  `Company` when `opportunity.company_id` is set. Load corpus `Document`s
  (char-budgeted, same `_CORPUS_CHAR_BUDGET` style as profile).
- Build a prompt that: states the role/company context (title, organization,
  summary, `details`, company fields); includes the corpus between markers; asks
  the model to answer the fixed expected questions (the `BriefingFactKey` members
  except `other`, plus any freeform `other` facts it deems useful) about THIS
  role; ground `why_fit`/`concerns` in the corpus; assign each fact a
  `confidence` (0–1) and a `source`; and **never invent specifics — leave
  unknown facts at low confidence with a null source** (anti-fabrication
  instruction, mirroring profile's "never invent" wording).
- Single-turn `query_fn`, collect text, `BriefingSchema.model_validate_json` via
  the same `_extract_json` helper approach as profile.
- Upsert ONE briefing per opportunity: find existing `Briefing` with this
  `opportunity_id`, else create. Set `summary`, `facts` (list of dicts via
  `fact.model_dump(mode="json")` — so the `BriefingFactKey` enum serializes to
  its string value for the JSON column), `company_id = opportunity.company_id`,
  `source_hash`
  (sha256 of the prompt input text), `generated_run_id` (from
  `current_run_id` contextvar if set, else None), `refreshed_at = _utcnow()`.

```python
def get_briefing(session: Session, opportunity_id: str) -> Briefing | None: ...
```

## 4. Agent write-back tool — `app/agent/tools.py`

New `@tool("synthesize_briefing", ...)`, args `{opportunity_id (required)}`.
Awaits `briefing_service.synthesize_briefing(s, opportunity_id=...)` (it reads
`current_run_id` itself), returns `_ok(f"Synthesized briefing for opportunity …")`.
Registered in `ALL_TOOLS`. Note: this triggers a nested single-turn LLM query
inside the agent run — acceptable per prior in-process concurrency validation.

## 5. API — `app/routers/opportunities.py`

- `POST /api/opportunities/{opp_id}/briefing/synthesize` → `Briefing` (async;
  calls `briefing_service.synthesize_briefing`; 404 if the opportunity is
  missing).
- `GET /api/opportunities/{opp_id}/briefing` → `Briefing | None` (via
  `get_briefing`).
- Add `"briefing": briefing_service.get_briefing(session, opp_id)` to the
  `get_opportunity` detail dict.

## 6. Frontend — `frontend/lib/api.ts` + `frontend/app/components/BriefingTab.tsx`

`api.ts`:
```typescript
export type BriefingFact = {
  key: string; question: string; answer: string;
  confidence: number | null; source: string | null;
};
export type Briefing = {
  id: number; opportunity_id: string | null; company_id: string | null;
  summary: string; facts: BriefingFact[];
  source_hash: string | null; generated_run_id: string | null;
  refreshed_at: string; created_at: string;
};
export async function fetchBriefing(oppId: string): Promise<Briefing | null> { ... } // GET .../briefing
export async function synthesizeBriefing(oppId: string): Promise<Briefing> { ... }   // POST .../briefing/synthesize
```

`BriefingTab.tsx`: takes the selected opportunity id as a prop. If none selected,
prompts the user to pick one (reusing the existing `selectedOpp` dropdown in
`page.tsx`). Shows a **Synthesize briefing** button (calls `synthesizeBriefing`,
shows a loading state, then re-fetches). Renders the briefing: `summary`, then a
list of facts — each row: question → answer, with a small confidence indicator
and `source` when present. Empty state when no briefing yet.

`page.tsx`: extend the `canvasTab` union with `"briefing"`, add a tab button
(styled like the existing Profile button), and render
`<BriefingTab opportunityId={selectedOpp} />` when active. `selectedOpp` already
exists (the capability dropdown).

## 7. Testing (TDD, backend; LLM stubbed)

Reuse the profile-test stub idiom (`_fake_query(reply_text, calls)` yielding an
`AssistantMessage`).

1. **Service** (`tests/test_briefing_synthesis.py`):
   - With an opportunity (+ linked company) and a seeded corpus, inject
     `query_fn=_fake_query(<canned BriefingSchema JSON>, calls)`:
     - a `Briefing` row is written for that opportunity with the parsed
       `summary`/`facts`; `company_id` matches; `source_hash` is non-empty.
     - the prompt contains the opportunity title, the company name, the corpus
       text (grounding), and an anti-fabrication instruction
       (`"never invent"` present).
   - Re-synthesize updates the SAME row (one briefing per opportunity).
   - Missing opportunity → `ValueError`.
2. **Tool** (`tests/test_briefing_tool.py`): monkeypatch
   `app.briefing_service.synthesize_briefing` with an async stub returning a
   `Briefing`; assert the tool forwards `opportunity_id` and returns an
   `_ok`-shaped result.
3. **API** (`tests/test_briefing_api.py`): monkeypatch
   `app.briefing_service.synthesize_briefing` (POST) and seed a row for GET;
   assert POST returns the row, `GET .../briefing` returns it (and `null` when
   none), and the opportunity-detail payload includes a `briefing` key.

All deterministic (temp SQLite via `conftest`; `briefings` already cleared in
`_clear_db`). No real LLM/API calls. Frontend verified via
`npm --prefix frontend run build` (the gate does not run `next build`).

## 8. Notes / risks

- Nested LLM query from the agent tool (tool → service → `query_fn`): validated
  safe by prior in-process concurrency testing; kept single-turn and bounded.
- Anti-fabrication relies on the prompt instruction + `confidence`/`source`
  fields; there is no programmatic grounding check (unlike artifact grounding),
  because briefing facts are about the external role/company, not the user's
  corpus. Acceptable: briefings are internal reference only.
- `source_hash` is stored for future staleness detection but not surfaced yet.
