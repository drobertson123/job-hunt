# Briefing Synthesis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Synthesize a structured per-opportunity Briefing (answers to expected questions, grounded in opportunity + company + corpus) via service, agent tool, API, and a frontend Briefing tab.

**Architecture:** `app/briefing_service.py` mirrors `app/profile_service.py` (single-turn tool-less local Claude CLI, Pydantic-validated, injectable `query_fn`). An agent `@tool` and two opportunity sub-routes call it; a frontend Briefing tab (keyed to the existing `selectedOpp`) shows/synthesizes it. The `Briefing` model and `BriefingFactKey` enum already exist.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, claude-agent-sdk (single-turn `query`), pydantic; Next.js/React/TypeScript frontend.

## Global Constraints

- Synthesis uses a single-turn, tool-less local Claude CLI session via the Agent SDK (`ClaudeAgentOptions(model=get_config().default_agent_model, max_turns=1)`), JSON validated by Pydantic — exactly like `profile_service`. `query_fn` is injectable for tests; tests NEVER call a real LLM.
- Anti-fabrication: the prompt must instruct "never invent" and require `confidence`/`source` per fact; unknown facts get low confidence + null source. No programmatic grounding check (briefings are internal reference; no approval gate).
- One Briefing per opportunity (upsert by `opportunity_id`).
- `facts` are persisted as `f.model_dump(mode="json")` so the `BriefingFactKey` enum serializes to its string value for the JSON column.
- Run attribution: the service takes a `generated_run_id` param; the agent tool passes `current_run_id.get()` (mirrors how `add_artifact` is run-attributed). The service does NOT import from `app.agent.tools` (avoids a circular import).
- Run backend tests with `.venv/bin/python -m pytest -q`; frontend verified with `npm --prefix frontend run build` (the gate does not run `next build`).
- `briefings` is already wiped per-test in `tests/conftest.py` `_clear_db`.
- Follow existing patterns: `profile_service`, `record_application` tool, `actions.py`/opportunity-detail routers, `fetchArtifacts`/canvas-tab wiring.

---

### Task 1: Service — `app/briefing_service.py`

**Files:**
- Create: `app/briefing_service.py`
- Test: `tests/test_briefing_synthesis.py`

**Interfaces:**
- Consumes: `Briefing`, `BriefingFactKey`, `Company`, `Document`, `Opportunity`, `_utcnow` (models); `get_config().default_agent_model`.
- Produces:
  - `class FactSchema(BaseModel)` (`key: BriefingFactKey = other`, `question: str`, `answer: str`, `confidence: float | None`, `source: str | None`)
  - `class BriefingSchema(BaseModel)` (`summary: str = ""`, `facts: list[FactSchema]`)
  - `async def synthesize_briefing(session, *, opportunity_id: str, generated_run_id: str | None = None, query_fn=sdk_query) -> Briefing`
  - `def get_briefing(session, opportunity_id: str) -> Briefing | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_briefing_synthesis.py
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from claude_agent_sdk import AssistantMessage, TextBlock
from sqlmodel import Session

from app.briefing_service import BriefingSchema, get_briefing, synthesize_briefing
from app.corpus_service import ingest_document
from app.db import engine
from app.models import (
    Company,
    DocumentMediaType,
    DocumentSource,
    Opportunity,
    OpportunityType,
)

_REPLY = (
    '{"summary": "Strong platform-eng fit.", "facts": ['
    '{"key": "salary_range", "question": "Salary range?", "answer": "unknown",'
    ' "confidence": 0.1, "source": null},'
    '{"key": "why_fit", "question": "Why a fit?", "answer": "MLOps depth.",'
    ' "confidence": 0.8, "source": "cv.md"}]}'
)


def _fake_query(reply_text: str, calls: list[dict]):
    async def fake(*, prompt, options) -> AsyncIterator:
        calls.append({"prompt": prompt, "options": options})
        yield AssistantMessage(content=[TextBlock(text=reply_text)], model="fake")
    return fake


def _fake_embedder(texts):
    return [[1.0, 0.0] for _ in texts]


async def test_synthesize_writes_row_and_grounds_prompt():
    with Session(engine) as s:
        co = Company(name="Globex", industry="Energy")
        s.add(co)
        s.commit()
        s.refresh(co)
        opp = Opportunity(type=OpportunityType.job, title="Staff ML Engineer",
                          organization="Globex", company_id=co.id,
                          summary="Own the ML platform.")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        ingest_document(s, title="cv.md", source_kind=DocumentSource.paste,
                        media_type=DocumentMediaType.md,
                        data=b"Jane Doe. MLOps, PyTorch.", embedder=_fake_embedder)
        opp_id = opp.id

    calls: list[dict] = []
    with Session(engine) as s:
        b = await synthesize_briefing(s, opportunity_id=opp_id,
                                      query_fn=_fake_query(_REPLY, calls))
        bid = b.id

    with Session(engine) as s:
        from app.models import Briefing
        row = s.get(Briefing, bid)
    assert row is not None
    assert row.opportunity_id == opp_id and row.company_id is not None
    assert row.summary == "Strong platform-eng fit."
    assert len(row.facts) == 2
    assert row.facts[0]["key"] == "salary_range"  # enum serialized to its value
    assert row.source_hash
    # grounding: opportunity title, company name, corpus, anti-fabrication instruction
    p = calls[0]["prompt"]
    assert "Staff ML Engineer" in p and "Globex" in p and "Jane Doe" in p
    assert "never invent" in p.lower()


async def test_synthesize_upserts_single_row_per_opportunity():
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        opp_id = opp.id
    calls: list[dict] = []
    with Session(engine) as s:
        first = await synthesize_briefing(s, opportunity_id=opp_id,
                                          query_fn=_fake_query(_REPLY, calls))
        first_id = first.id
        second = await synthesize_briefing(s, opportunity_id=opp_id,
                                           query_fn=_fake_query(_REPLY, calls))
        assert second.id == first_id
        assert get_briefing(s, opp_id) is not None


async def test_synthesize_missing_opportunity_raises():
    with Session(engine) as s:
        with pytest.raises(ValueError):
            await synthesize_briefing(s, opportunity_id="nope",
                                      query_fn=_fake_query(_REPLY, []))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_briefing_synthesis.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.briefing_service'`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/briefing_service.py
"""Briefing synthesis: read an opportunity (+ company + corpus) and write a
structured Briefing row of answers to expected questions.

Mirrors profile_service: single-turn, tool-less local Claude CLI session
(Agent SDK, CLI auth — no API key), JSON validated by Pydantic, injectable
query_fn for tests.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock
from claude_agent_sdk import query as sdk_query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.config import get_config
from app.models import (
    Briefing,
    BriefingFactKey,
    Company,
    Document,
    Opportunity,
    _utcnow,
)

_CORPUS_CHAR_BUDGET = 12000


class FactSchema(BaseModel):
    key: BriefingFactKey = BriefingFactKey.other
    question: str
    answer: str
    confidence: float | None = None
    source: str | None = None


class BriefingSchema(BaseModel):
    summary: str = ""
    facts: list[FactSchema] = Field(default_factory=list)


_EXPECTED = ", ".join(k.value for k in BriefingFactKey if k != BriefingFactKey.other)

_INSTRUCTION = (
    "You build a concise briefing about a single job opportunity for the "
    "candidate. Answer these expected questions when the context supports them: "
    f"{_EXPECTED}. Tag each fact with the matching `key` (use \"other\" for "
    "anything extra). Ground why_fit and concerns in the candidate's own "
    "documents. Give each fact a confidence in [0,1] and a source. NEVER invent "
    "specifics (salary numbers, policies, names): if a fact is not supported by "
    "the context, give it a low confidence and a null source — never invent."
)


def _build_prompt(opp_text: str, corpus_text: str) -> str:
    schema = json.dumps(BriefingSchema.model_json_schema())
    return (
        f"{_INSTRUCTION}\n\n"
        "Respond with ONE JSON object and nothing else — no prose, no code fences. "
        f"It must conform to this JSON Schema:\n{schema}\n\n"
        "The opportunity (and company):\n"
        f"<opportunity>\n{opp_text}\n</opportunity>\n\n"
        "The candidate's documents:\n"
        f"<corpus>\n{corpus_text}\n</corpus>"
    )


def _extract_json(text: str) -> str:
    s = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        return s[start : end + 1]
    return s


def _opportunity_text(session: Session, opp: Opportunity) -> str:
    parts = [f"Title: {opp.title}"]
    if opp.organization:
        parts.append(f"Organization: {opp.organization}")
    if opp.location:
        parts.append(f"Location: {opp.location}")
    if opp.summary:
        parts.append(f"Summary: {opp.summary}")
    if opp.details:
        parts.append(f"Details: {json.dumps(opp.details)}")
    if opp.company_id:
        company = session.get(Company, opp.company_id)
        if company:
            extra = ""
            if company.industry:
                extra += f" — industry {company.industry}"
            if company.summary:
                extra += f"; {company.summary}"
            parts.append(f"Company: {company.name}{extra}")
    return "\n".join(parts)


async def synthesize_briefing(
    session: Session,
    *,
    opportunity_id: str,
    generated_run_id: str | None = None,
    query_fn: Callable[..., AsyncIterator[Any]] = sdk_query,
) -> Briefing:
    opp = session.get(Opportunity, opportunity_id)
    if opp is None:
        raise ValueError(f"opportunity {opportunity_id} not found")
    opp_text = _opportunity_text(session, opp)
    docs = session.exec(select(Document).order_by(Document.created_at)).all()
    corpus_text = "\n\n".join(
        f"# {d.title}\n{d.raw_text}" for d in docs
    )[:_CORPUS_CHAR_BUDGET]
    prompt = _build_prompt(opp_text, corpus_text)

    model = get_config().default_agent_model
    options = ClaudeAgentOptions(model=model, max_turns=1)
    chunks: list[str] = []
    async for message in query_fn(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock) and block.text:
                    chunks.append(block.text)
    parsed = BriefingSchema.model_validate_json(_extract_json("".join(chunks)))

    row = session.exec(
        select(Briefing).where(Briefing.opportunity_id == opportunity_id)
    ).first()
    if row is None:
        row = Briefing(opportunity_id=opportunity_id)
    row.company_id = opp.company_id
    row.summary = parsed.summary
    row.facts = [f.model_dump(mode="json") for f in parsed.facts]
    row.source_hash = hashlib.sha256(prompt.encode()).hexdigest()
    row.generated_run_id = generated_run_id
    row.refreshed_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_briefing(session: Session, opportunity_id: str) -> Briefing | None:
    return session.exec(
        select(Briefing).where(Briefing.opportunity_id == opportunity_id)
    ).first()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_briefing_synthesis.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/briefing_service.py tests/test_briefing_synthesis.py
git commit -m "feat(briefing): synthesize_briefing service (opp+company+corpus)"
```

---

### Task 2: Agent write-back tool — `synthesize_briefing`

**Files:**
- Modify: `app/agent/tools.py` (import `briefing_service`; add `@tool`; add to `ALL_TOOLS`)
- Test: `tests/test_briefing_tool.py`

**Interfaces:**
- Consumes: `briefing_service.synthesize_briefing` (Task 1); existing `_ok`, `Session`, `engine`, `current_run_id`.
- Produces: async tool `synthesize_briefing(args: dict) -> dict`; registered name `mcp__app__synthesize_briefing`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_briefing_tool.py
from __future__ import annotations

import pytest
from sqlmodel import Session

from app import briefing_service
from app.agent import tools
from app.db import engine
from app.models import Briefing, Opportunity, OpportunityType


@pytest.mark.asyncio
async def test_synthesize_briefing_tool_forwards_and_returns_ok(monkeypatch):
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        opp_id = opp.id

    seen = {}

    async def fake(session, *, opportunity_id, generated_run_id=None, **kw):
        seen["opportunity_id"] = opportunity_id
        b = Briefing(opportunity_id=opportunity_id, summary="x",
                     facts=[{"key": "why_fit", "question": "q", "answer": "a",
                             "confidence": 0.5, "source": None}])
        session.add(b)
        session.commit()
        session.refresh(b)
        return b

    monkeypatch.setattr(briefing_service, "synthesize_briefing", fake)
    res = await tools.synthesize_briefing({"opportunity_id": opp_id})
    assert seen["opportunity_id"] == opp_id
    assert res["content"][0]["type"] == "text"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_briefing_tool.py -v`
Expected: FAIL with `AttributeError: module 'app.agent.tools' has no attribute 'synthesize_briefing'`.

- [ ] **Step 3: Write minimal implementation**

In `app/agent/tools.py`, change the existing `from app import corpus_service, services` import to `from app import briefing_service, corpus_service, services`. Add this tool after `record_application`:

```python
@tool(
    "synthesize_briefing",
    "Synthesize a structured briefing (salary, remote, tech stack, why-fit, "
    "concerns, ...) for an opportunity, grounded in its data and the user's corpus.",
    {
        "type": "object",
        "properties": {"opportunity_id": {"type": "string"}},
        "required": ["opportunity_id"],
    },
)
async def synthesize_briefing(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        briefing = await briefing_service.synthesize_briefing(
            s,
            opportunity_id=args["opportunity_id"],
            generated_run_id=current_run_id.get(),
        )
        return _ok(
            f"Synthesized briefing for opportunity {briefing.opportunity_id} "
            f"({len(briefing.facts)} facts)."
        )
```

Add `synthesize_briefing` to the `ALL_TOOLS` list (after `record_application`).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_briefing_tool.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/agent/tools.py tests/test_briefing_tool.py
git commit -m "feat(tools): synthesize_briefing write-back tool"
```

---

### Task 3: API — synthesize + get + detail include

**Files:**
- Modify: `app/routers/opportunities.py` (import `briefing_service` + `Briefing`; two routes; detail include)
- Test: `tests/test_briefing_api.py`

**Interfaces:**
- Consumes: `briefing_service.synthesize_briefing`, `briefing_service.get_briefing` (Task 1).
- Produces: `POST /api/opportunities/{opp_id}/briefing/synthesize` → `Briefing`; `GET /api/opportunities/{opp_id}/briefing` → `Briefing | None`; `briefing` key on `GET /api/opportunities/{opp_id}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_briefing_api.py
from __future__ import annotations

from sqlmodel import Session

from app import briefing_service
from app.db import engine
from app.models import Briefing, Opportunity, OpportunityType


def _make_opp() -> str:
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        return opp.id


def test_synthesize_endpoint_returns_briefing(client, monkeypatch):
    opp_id = _make_opp()

    async def fake(session, *, opportunity_id, generated_run_id=None, **kw):
        b = Briefing(opportunity_id=opportunity_id, summary="ok",
                     facts=[{"key": "why_fit", "question": "q", "answer": "a",
                             "confidence": 0.9, "source": None}])
        session.add(b)
        session.commit()
        session.refresh(b)
        return b

    monkeypatch.setattr(briefing_service, "synthesize_briefing", fake)
    res = client.post(f"/api/opportunities/{opp_id}/briefing/synthesize")
    assert res.status_code == 200
    assert res.json()["summary"] == "ok"


def test_get_briefing_endpoint_and_detail_include(client):
    opp_id = _make_opp()
    # none yet
    assert client.get(f"/api/opportunities/{opp_id}/briefing").json() is None
    with Session(engine) as s:
        s.add(Briefing(opportunity_id=opp_id, summary="hi", facts=[]))
        s.commit()
    got = client.get(f"/api/opportunities/{opp_id}/briefing")
    assert got.status_code == 200 and got.json()["summary"] == "hi"
    detail = client.get(f"/api/opportunities/{opp_id}")
    assert "briefing" in detail.json() and detail.json()["briefing"]["summary"] == "hi"


def test_synthesize_missing_opportunity_404(client):
    res = client.post("/api/opportunities/nope/briefing/synthesize")
    assert res.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_briefing_api.py -v`
Expected: FAIL — routes 404 / `KeyError: 'briefing'`.

- [ ] **Step 3a: Add imports to `app/routers/opportunities.py`**

Change `from app import services` to `from app import briefing_service, services`. Add `Briefing` to the `from app.models import (...)` block.

- [ ] **Step 3b: Add the detail include**

In `get_opportunity`'s returned dict, add beside `"actions"`:

```python
        "briefing": briefing_service.get_briefing(session, opp_id),
```

- [ ] **Step 3c: Add the two routes** (after `get_opportunity`, before `update_stage`)

```python
@router.post("/{opp_id}/briefing/synthesize", response_model=Briefing)
async def synthesize_briefing_endpoint(
    opp_id: str, session: Session = Depends(get_session)
) -> Briefing:
    try:
        return await briefing_service.synthesize_briefing(session, opportunity_id=opp_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{opp_id}/briefing", response_model=Briefing | None)
def get_briefing_endpoint(
    opp_id: str, session: Session = Depends(get_session)
) -> Briefing | None:
    return briefing_service.get_briefing(session, opp_id)
```

- [ ] **Step 4: Run the new tests, then full suite + gate**

Run: `.venv/bin/python -m pytest tests/test_briefing_api.py -v`
Expected: PASS (3 tests).
Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all).
Run: `scripts/ci/gate.sh`
Expected: GATE PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/routers/opportunities.py tests/test_briefing_api.py
git commit -m "feat(api): briefing synthesize + get + detail include"
```

---

### Task 4: Frontend — Briefing tab

**Files:**
- Modify: `frontend/lib/api.ts` (types + `fetchBriefing`/`synthesizeBriefing`)
- Create: `frontend/app/components/BriefingTab.tsx`
- Modify: `frontend/app/page.tsx` (tab union, button, render with `selectedOpp`)

**Interfaces:**
- Consumes: `POST/GET /api/opportunities/{id}/briefing*` (Task 3); existing `selectedOpp` state.
- Produces: `Briefing`/`BriefingFact` TS types, `fetchBriefing`/`synthesizeBriefing`, `<BriefingTab opportunityId=... />`.

- [ ] **Step 1: Add types + fetchers to `frontend/lib/api.ts`**

After the `Application` type (or any existing type), add:

```typescript
export type BriefingFact = {
  key: string;
  question: string;
  answer: string;
  confidence: number | null;
  source: string | null;
};

export type Briefing = {
  id: number;
  opportunity_id: string | null;
  company_id: string | null;
  summary: string;
  facts: BriefingFact[];
  source_hash: string | null;
  generated_run_id: string | null;
  refreshed_at: string;
  created_at: string;
};

export async function fetchBriefing(oppId: string): Promise<Briefing | null> {
  const res = await fetch(`/api/opportunities/${oppId}/briefing`);
  if (!res.ok) throw new Error(`briefing failed: ${res.status}`);
  return res.json();
}

export async function synthesizeBriefing(oppId: string): Promise<Briefing> {
  const res = await fetch(`/api/opportunities/${oppId}/briefing/synthesize`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`synthesize briefing failed: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Create `frontend/app/components/BriefingTab.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { Briefing, fetchBriefing, synthesizeBriefing } from "@/lib/api";

export default function BriefingTab({ opportunityId }: { opportunityId: string }) {
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (!opportunityId) {
      setBriefing(null);
      return;
    }
    fetchBriefing(opportunityId).then(setBriefing).catch(() => setBriefing(null));
  }, [opportunityId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!opportunityId) {
    return (
      <p className="p-4 text-sm text-gray-500">
        Select an opportunity above to see or generate its briefing.
      </p>
    );
  }

  const synth = async () => {
    setBusy(true);
    try {
      setBriefing(await synthesizeBriefing(opportunityId));
    } catch {
      // leave existing briefing in place on failure
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 p-2">
      <button
        onClick={synth}
        disabled={busy}
        className="self-start rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        {busy ? "Synthesizing…" : briefing ? "Re-synthesize briefing" : "Synthesize briefing"}
      </button>

      {!briefing && (
        <p className="text-sm text-gray-500">No briefing yet.</p>
      )}

      {briefing && (
        <div className="flex flex-col gap-2 text-sm">
          {briefing.summary && <p className="text-gray-800">{briefing.summary}</p>}
          {briefing.facts.map((f, i) => (
            <div key={i} className="rounded border border-gray-200 p-2">
              <div className="font-medium">{f.question}</div>
              <div>{f.answer}</div>
              <div className="text-xs text-gray-500">
                {f.confidence != null && `confidence ${f.confidence.toFixed(2)}`}
                {f.source && ` · source: ${f.source}`}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Wire the tab into `frontend/app/page.tsx`**

1. Import: `import BriefingTab from "./components/BriefingTab";`
2. Add `fetchBriefing`/`synthesizeBriefing`/`Briefing` to the `@/lib/api` import only if you reference them in page.tsx — the tab is self-contained, so you only need the `BriefingTab` import. Do NOT add briefing state to page.tsx.
3. Widen the tab union (read the current line and add `"briefing"`):
```tsx
  const [canvasTab, setCanvasTab] = useState<"workspace" | "profile" | "applications" | "briefing">("workspace");
```
4. Add a tab button beside the others (copy the EXACT className strings from the existing Profile/Applications buttons in the file):
```tsx
            <button
              className={/* same active/inactive className expression as the Profile button */ ""}
              onClick={() => setCanvasTab("briefing")}
            >
              Briefing
            </button>
```
5. In the render switch, add a branch (place it alongside the existing `applications`/`profile` branches), passing the existing `selectedOpp`:
```tsx
          ) : canvasTab === "briefing" ? (
            <BriefingTab opportunityId={selectedOpp} />
```

(Read `page.tsx` before editing: match the real button className strings and the exact shape of the existing tab-render ternary; leave the workspace block unchanged.)

- [ ] **Step 4: Verify the frontend builds**

Run: `npm --prefix frontend run build`
Expected: "Compiled successfully", no type errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/app/components/BriefingTab.tsx frontend/app/page.tsx
git commit -m "feat(ui): Briefing canvas tab with synthesize button"
```

---

## Final verification

- [ ] `.venv/bin/python -m pytest -q` → all pass.
- [ ] `scripts/ci/gate.sh` → GATE PASSED.
- [ ] `npm --prefix frontend run build` → Compiled successfully.
- [ ] `git log --oneline` shows 4 focused commits on `feature/briefing-synthesis`.

## Self-Review (completed by plan author)

- **Spec coverage:** service synth+get with opp+company+corpus and anti-fabrication prompt (T1, spec §3, §7); agent tool (T2, §4); API synth+get+detail include (T3, §5); frontend types/fetchers/tab keyed to `selectedOpp` (T4, §6); LLM stubbed via injected `query_fn` (T1) and monkeypatched service (T2, T3) (§7); one-briefing-per-opportunity upsert (T1); `model_dump(mode="json")` enum serialization (T1, §3 + global constraint).
- **Deviation from spec (intentional):** spec §3/§4 said the service reads the `current_run_id` contextvar; the plan instead passes `generated_run_id` as a param and the tool supplies `current_run_id.get()`. This avoids a circular import (`briefing_service` ↔ `app.agent.tools`) and matches the existing run-attribution pattern. Functionally equivalent.
- **Placeholder scan:** none — all code is concrete except T4 step 3's button className, which is intentionally "copy the real file's existing button classes" (the same instruction the prior Applications-tab task used successfully); flagged so the implementer reads page.tsx.
- **Type consistency:** `synthesize_briefing(session, *, opportunity_id, generated_run_id=None, query_fn=sdk_query)` identical across T1 def, T2 tool call (`generated_run_id=current_run_id.get()`), T3 endpoint call. `Briefing`/`BriefingFact` TS fields match the model's serialized columns. `facts[i]["key"]` is a string post-`model_dump(mode="json")`, matching the T1 assertion and the TS `key: string`.
