# Content Library Implementation Plan (Phase C)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A reusable Content Library (headline/summary/bullet blocks) synthesized from the corpus and reused by cv-tailor.

## Global Constraints
- New table via `create_all` (no migration). Writes through the service/tool layer (Constitution II); blocks corpus-grounded.
- pytest: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest …`. Frontend: `npm --prefix frontend install` then build. Verify: `bash scripts/ci/gate.sh` GREEN + frontend build.
- Do NOT invoke any finishing/branch skill — stop after committing and reporting.

---

### Task 1: Model + service + tool + API

**Files:**
- Modify: `app/models.py` (`ContentBlockKind` + `ContentBlock`)
- Modify: `app/services.py` (add/list/delete)
- Modify: `app/agent/tools.py` (`save_content_block` → `ALL_TOOLS`)
- Create: `app/routers/content.py`; Modify: `app/main.py` (mount)
- Test: `tests/test_content_blocks.py`

- [ ] **Step 1: Model**

In `app/models.py` (near the other content models), add:
```python
class ContentBlockKind(str, Enum):
    headline = "headline"
    summary = "summary"
    bullet = "bullet"
    other = "other"


class ContentBlock(SQLModel, table=True):
    __tablename__ = "content_blocks"

    id: int | None = Field(default=None, primary_key=True)
    kind: ContentBlockKind = ContentBlockKind.bullet
    audience: str = ""
    text: str
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    provenance: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
```

- [ ] **Step 2: Failing test**

Create `tests/test_content_blocks.py`:
```python
from sqlmodel import Session

from app.db import engine
from app import services
from app.models import ContentBlockKind


def test_add_list_delete_content_block():
    with Session(engine) as s:
        b = services.add_content_block(s, kind=ContentBlockKind.headline, text="IIoT & Digital Twin Leader", audience="technical", tags=["iiot"])
        assert b.id is not None
        assert any(x.id == b.id for x in services.list_content_blocks(s))
        assert services.list_content_blocks(s, kind=ContentBlockKind.summary) == []
        assert services.delete_content_block(s, b.id) is True
        assert services.delete_content_block(s, b.id) is False


def test_save_content_block_tool_persists():
    import asyncio
    from app.agent.tools import save_content_block
    res = asyncio.run(save_content_block({"text": "Scaled platform 10x", "kind": "bullet", "tags": ["scale"]}))
    assert res["content"][0]["text"].startswith("Saved content block")
    with Session(engine) as s:
        assert any(x.text == "Scaled platform 10x" for x in services.list_content_blocks(s))


def test_content_blocks_api(client):
    r = client.post  # noqa: F841 (writes go via tool; just exercise GET/DELETE)
    # seed via service
    from app.db import engine as e
    with Session(e) as s:
        b = services.add_content_block(s, kind=ContentBlockKind.bullet, text="Led 30 engineers")
        bid = b.id
    got = client.get("/api/content-blocks").json()
    assert any(x["id"] == bid for x in got)
    assert client.delete(f"/api/content-blocks/{bid}").status_code == 204
    assert client.delete(f"/api/content-blocks/{bid}").status_code == 404
```

- [ ] **Step 3: Run → fail.**

- [ ] **Step 4: Service**

In `app/services.py` (add `ContentBlock, ContentBlockKind` to the models import), add:
```python
def add_content_block(
    session: Session,
    *,
    kind: ContentBlockKind = ContentBlockKind.bullet,
    text: str,
    audience: str = "",
    tags: list[str] | None = None,
    provenance: str | None = None,
) -> ContentBlock:
    block = ContentBlock(kind=kind, text=text, audience=audience, tags=tags or [], provenance=provenance)
    session.add(block)
    session.commit()
    session.refresh(block)
    return block


def list_content_blocks(session: Session, *, kind: ContentBlockKind | None = None) -> list[ContentBlock]:
    stmt = select(ContentBlock)
    if kind is not None:
        stmt = stmt.where(ContentBlock.kind == kind)
    return list(session.exec(stmt.order_by(ContentBlock.created_at.desc())).all())


def delete_content_block(session: Session, block_id: int) -> bool:
    block = session.get(ContentBlock, block_id)
    if block is None:
        return False
    session.delete(block)
    session.commit()
    return True
```

- [ ] **Step 5: Tool**

In `app/agent/tools.py`, add `ContentBlockKind` to the models import and define (near the other write-back tools):
```python
@tool(
    "save_content_block",
    "Save a reusable career content block (headline, summary, or achievement bullet) to the library.",
    {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "kind": {"type": "string", "enum": ["headline", "summary", "bullet", "other"]},
            "audience": {"type": "string", "description": "positioning tag, e.g. technical / leadership"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["text"],
    },
)
async def save_content_block(args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as s:
        block = services.add_content_block(
            s,
            kind=_enum(ContentBlockKind, args.get("kind"), ContentBlockKind.bullet),
            text=args.get("text") or "",
            audience=args.get("audience") or "",
            tags=args.get("tags") or [],
            provenance="career-pack:content-library",
        )
        return _ok(f"Saved content block #{block.id} ({block.kind.value}).")
```
Add `save_content_block` to `ALL_TOOLS`.

- [ ] **Step 6: Router + mount**

Create `app/routers/content.py`:
```python
"""Content-library endpoints — read + delete (writes go through the agent tool)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session

from app import services
from app.db import get_session
from app.models import ContentBlock, ContentBlockKind

router = APIRouter(prefix="/api/content-blocks", tags=["content-blocks"])


@router.get("")
def list_content_blocks(
    kind: ContentBlockKind | None = None, session: Session = Depends(get_session)
) -> list[ContentBlock]:
    return services.list_content_blocks(session, kind=kind)


@router.delete("/{block_id}", status_code=204)
def delete_content_block(block_id: int, session: Session = Depends(get_session)) -> Response:
    if not services.delete_content_block(session, block_id):
        raise HTTPException(status_code=404, detail="content block not found")
    return Response(status_code=204)
```
In `app/main.py`: add `content` to the routers import and `app.include_router(content.router)`.

- [ ] **Step 7: Run tests + gate** → PASS / GATE PASSED.

- [ ] **Step 8: Commit**

```bash
git add app/models.py app/services.py app/agent/tools.py app/routers/content.py app/main.py tests/test_content_blocks.py
git commit -m "feat(content): ContentBlock model + save_content_block tool + content-blocks API"
```

---

### Task 2: content-library capability + reuse in cv-tailor

**Files:**
- Modify: `app/capabilities.py` (`include_content` + `content_library_block` + build_prompt + entry)
- Modify: `app/routers/capabilities.py` (fetch content blocks for `include_content`)
- Create: `skills/career-pack/skills/content-library/SKILL.md`
- Modify: `skills/career-pack/skills/cv-tailor/SKILL.md` (a reuse step)
- Modify (counts 15→16): `tests/test_career_pack.py`, `tests/test_capabilities.py`, `tests/test_capabilities_api.py`, `tests/test_integration_smoke.py`
- Test: `tests/test_content_prompt.py`

- [ ] **Step 1: Count + registry updates (red first)**

Add `"content-library"` to `EXPECTED_SKILLS` (test_career_pack) and the `by_name` set (test_capabilities_api); bump all four `15`→`16` (test_career_pack, test_capabilities, test_capabilities_api, test_integration_smoke); add `"content-library"` to the registry name-set in test_capabilities if present.

- [ ] **Step 2: Prompt test (red)**

Create `tests/test_content_prompt.py`:
```python
from sqlmodel import Session

from app.db import engine
from app import capabilities as caps, services
from app.models import ContentBlockKind, Opportunity, OpportunityType


def _cap(name):
    return next(c for c in caps.CAPABILITIES if c.name == name)


def test_cv_tailor_prompt_includes_content_library():
    with Session(engine) as s:
        services.add_content_block(s, kind=ContentBlockKind.headline, text="Digital Twin Leader", audience="technical")
        blocks = services.list_content_blocks(s)
    opp = Opportunity(type=OpportunityType.job, title="Role", organization="Co")
    prompt = caps.build_prompt(_cap("cv-tailor"), opportunity=opp, content_blocks=blocks)
    assert "Content library" in prompt and "Digital Twin Leader" in prompt


def test_cover_letter_prompt_omits_content_library():
    opp = Opportunity(type=OpportunityType.job, title="Role", organization="Co")
    prompt = caps.build_prompt(_cap("cover-letter"), opportunity=opp, content_blocks=[])
    assert "Content library" not in prompt
```

- [ ] **Step 3: Capabilities wiring**

In `app/capabilities.py`:
- Add `include_content: bool = False` to the `Capability` dataclass (after `include_contacts`).
- Set `include_content=True` on the `cv-tailor` entry.
- Add `content-library` entry (after `cv-tailor` or near the other career skills):
```python
    Capability(
        name="content-library",
        skill="content-library",
        label="Build content library",
        description="Synthesize a reusable library of headline/summary/bullet variants from your corpus.",
        requires_opportunity=False,
        requires_input=False,
        include_profile=True,
        plugin=CAREER_PLUGIN,
    ),
```
- Add a helper:
```python
def content_library_block(blocks: list["ContentBlock"] | None) -> str:
    if not blocks:
        return "- (content library empty — run the content-library capability to build it)"
    by_kind: dict[str, list[str]] = {}
    for b in blocks:
        tag = f" [{b.audience}]" if b.audience else ""
        by_kind.setdefault(b.kind.value, []).append(f"{b.text}{tag}")
    lines = []
    for kind in ("headline", "summary", "bullet", "other"):
        items = by_kind.get(kind)
        if items:
            lines.append(f"{kind}s:")
            lines.extend(f"  - {t}" for t in items[:12])
    return "\n".join(lines)
```
(Import `ContentBlock` with the other models.)
- In `build_prompt`, add a param `content_blocks: list["ContentBlock"] | None = None`, and after the contacts block append:
```python
    if cap.include_content:
        parts.append("Content library (reuse/adapt these vetted blocks where they fit):\n" + content_library_block(content_blocks))
```

- [ ] **Step 4: Router fetch**

In `app/routers/capabilities.py` `invoke`, add:
```python
    content_blocks = services.list_content_blocks(session) if cap.include_content else None
```
and pass `content_blocks=content_blocks` to `build_prompt`.

- [ ] **Step 5: content-library skill**

Create `skills/career-pack/skills/content-library/SKILL.md`:
```markdown
---
name: content-library
description: Use to build or refresh the reusable content library — headline, summary, and achievement-bullet variants synthesized from the user's corpus.
---

# Content Library

Synthesize a small, reusable library of polished career blocks the tailoring
skills draw from. Everything must be grounded in the user's corpus — never invent
a metric, title, employer, or claim.

## Steps

1. Read the Candidate profile block. Call `mcp__app__search_corpus` several times
   for the user's strongest material (leadership, scale, domain wins, tooling).
2. From grounded material, compose:
   - **2-3 `headline` variants** — different positioning angles (e.g. a technical
     angle and a leadership angle). `audience` names the angle.
   - **2-3 `summary` variants** — 2-3 sentences each, audience-tailored
     (e.g. `technical`, `leadership`). `audience` names it.
   - **up to 10 `bullet`s** — the strongest achievement statements
     (action + scope + outcome), each traceable to a corpus passage.
3. For each block, call `mcp__app__save_content_block` (contract below). If a
   claim isn't supported by the corpus, do NOT save it.
4. Reply with how many blocks of each kind you saved.

## Write-back contract (MUST)

- `mcp__app__save_content_block` per block — `text` (the block), `kind`
  (`headline`/`summary`/`bullet`), `audience` (the angle, optional), `tags`
  (skills/domains it supports). Save only corpus-grounded content.
```

- [ ] **Step 6: cv-tailor reuse step**

In `skills/career-pack/skills/cv-tailor/SKILL.md`, add a step early in its workflow
(keep frontmatter, `## Write-back contract`, `mcp__app__` markers): instruct the
agent that a **Content library** block may be present in the prompt — prefer
selecting/adapting the headline and summary variant that best fits THIS role and
reusing matching achievement bullets, rather than writing from scratch; all reused
claims must still be grounded (the library is already corpus-grounded). One or two
sentences is enough.

- [ ] **Step 7: Run tests + gate** → PASS / GATE PASSED.

- [ ] **Step 8: Commit**

```bash
git add app/capabilities.py app/routers/capabilities.py skills/career-pack/skills/content-library skills/career-pack/skills/cv-tailor/SKILL.md tests/
git commit -m "feat(content): content-library capability + cv-tailor reuses the library"
```

---

### Task 3: Library UI tab

**Files:**
- Modify: `frontend/lib/api.ts` (ContentBlock type + fetchers)
- Create: `frontend/app/components/LibraryTab.tsx`
- Modify: `frontend/app/page.tsx` (canvas union, LeftNav handled separately — add to LeftNav too), `frontend/app/components/LeftNav.tsx`

- [ ] **Step 1: api.ts**

```ts
export type ContentBlock = {
  id: number;
  kind: string;
  audience: string;
  text: string;
  tags: string[];
  created_at: string;
};

export async function fetchContentBlocks(): Promise<ContentBlock[]> {
  const res = await fetch("/api/content-blocks");
  if (!res.ok) throw new Error(`content blocks failed: ${res.status}`);
  return res.json();
}

export async function deleteContentBlock(id: number): Promise<void> {
  const res = await fetch(`/api/content-blocks/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`delete content block failed: ${res.status}`);
}
```

- [ ] **Step 2: LibraryTab.tsx**

Model on an existing simple tab (read `ActionsTab.tsx` for the FetchError/load/Tailwind idiom). Create `frontend/app/components/LibraryTab.tsx`: load `fetchContentBlocks`, group by `kind` (headlines / summaries / bullets), render each block with its `audience` tag and a Remove button (`deleteContentBlock(id).then(load)`); `FetchError` on load failure; empty-state text suggesting the `content-library` capability. Use TwinForge tokens. No props.

- [ ] **Step 3: Wire into the shell**

- `frontend/app/components/LeftNav.tsx`: add `{ key: "library", label: "Library" }` to the **You** section (or **Research**).
- `frontend/app/page.tsx`: import `LibraryTab`; add `| "library"` to the `canvasTab` union; add a render branch `) : canvasTab === "library" ? ( <LibraryTab /> )`.

- [ ] **Step 4: Build**

Run: `npm --prefix frontend install` then `npm --prefix frontend run build` → succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/app/components/LibraryTab.tsx frontend/app/components/LeftNav.tsx frontend/app/page.tsx
git commit -m "feat(content): Library tab — view/remove reusable content blocks"
```
