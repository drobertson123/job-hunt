# Relationships & Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A **Relationships** screen showing the network around each company — your contacts (warm intros) and the roles you're tracking there — via a new `GET /api/relationships` aggregation.

## Global Constraints
- Real data only (contacts + opportunities joined by company). No new deps. Frontend renders a clustered "network" view (hub = company; spokes = contacts + roles) with plain SVG/flex — no graph library.
- pytest: `/home/drobertson123/src/job-hunt/.venv/bin/python -m pytest …`. Frontend build must pass. Gate green. Add `relationships` to the union + rail + a render branch.
- Do NOT invoke any finishing/branch skill — stop after committing.

---

### Task 1: `relationships_service` + `GET /api/relationships`

**Files:** Create `app/relationships_service.py`, `app/routers/relationships.py`; Modify `app/main.py`; Test `tests/test_relationships.py`.

- [ ] **Step 1: Failing test**

Create `tests/test_relationships.py`:
```python
from sqlmodel import Session

from app.db import engine
from app import relationships_service as rs, services
from app.models import Company, Opportunity, OpportunityType


def test_relationships_cluster_with_contact_and_role():
    with Session(engine) as s:
        co = Company(name="Stripe")
        s.add(co); s.commit(); s.refresh(co)
        services.add_contact(s, name="Jane Smith", role="EM", organization="Stripe", )
        s.add(Opportunity(type=OpportunityType.job, title="Staff Eng", organization="Stripe"))
        s.commit()
        out = rs.compute_relationships(s)
    stripe = next((c for c in out["clusters"] if c["name"] == "Stripe"), None)
    assert stripe is not None
    assert any(p["name"] == "Jane Smith" for p in stripe["contacts"])
    assert any(o["title"] == "Staff Eng" for o in stripe["opportunities"])
    assert out["warm_intro_count"] >= 1


def test_relationships_endpoint(client):
    r = client.get("/api/relationships")
    assert r.status_code == 200
    assert "clusters" in r.json() and "warm_intro_count" in r.json()
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement `app/relationships_service.py`**

```python
"""Network of contacts <-> companies <-> opportunities (deterministic aggregation)."""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.models import Company, Contact, Opportunity


def _key(company_id: str | None, org: str | None, names: dict[str, str]):
    if company_id and company_id in names:
        return ("co", company_id), names[company_id]
    name = (org or "").strip()
    if not name:
        return None, ""
    return ("org", name.lower()), name


def compute_relationships(session: Session) -> dict[str, Any]:
    names = {c.id: c.name for c in session.exec(select(Company)).all()}
    clusters: dict[tuple, dict[str, Any]] = {}

    def cluster(k, display) -> dict[str, Any]:
        return clusters.setdefault(k, {"name": display, "contacts": [], "opportunities": []})

    for ct in session.exec(select(Contact)).all():
        k, disp = _key(ct.company_id, ct.organization, names)
        if k is None:
            continue
        cluster(k, disp)["contacts"].append({"id": ct.id, "name": ct.name, "role": ct.role})

    for o in session.exec(select(Opportunity).where(Opportunity.archived == False)).all():  # noqa: E712
        k, disp = _key(o.company_id, o.organization, names)
        if k is None:
            continue
        cluster(k, disp)["opportunities"].append({"id": o.id, "title": o.title, "stage": o.stage.value})

    out = [
        {**v, "score": len(v["contacts"]) + len(v["opportunities"]), "warm": bool(v["contacts"]) and bool(v["opportunities"])}
        for v in clusters.values()
    ]
    out.sort(key=lambda c: (c["warm"], c["score"]), reverse=True)
    return {"clusters": out[:40], "warm_intro_count": sum(1 for c in out if c["warm"])}
```

- [ ] **Step 4: Router + mount**

Create `app/routers/relationships.py`:
```python
"""Relationships / network endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import relationships_service
from app.db import get_session

router = APIRouter(prefix="/api/relationships", tags=["relationships"])


@router.get("")
def get_relationships(session: Session = Depends(get_session)) -> dict:
    return relationships_service.compute_relationships(session)
```
Mount in `app/main.py` (`relationships` in routers import + `app.include_router(relationships.router)`).

- [ ] **Step 5: Run tests + gate** → PASS / GATE PASSED.

- [ ] **Step 6: Commit**

```bash
git add app/relationships_service.py app/routers/relationships.py app/main.py tests/test_relationships.py
git commit -m "feat(relationships): contacts<->companies<->opportunities aggregation + GET /api/relationships"
```

---

### Task 2: Relationships screen

**Files:** Modify `frontend/lib/api.ts`; Create `frontend/app/components/RelationshipsTab.tsx`; Modify `frontend/app/page.tsx`, `frontend/app/components/IconRail.tsx`.

- [ ] **Step 1: api.ts**

```ts
export type RelCluster = {
  name: string;
  contacts: { id: number; name: string; role: string | null }[];
  opportunities: { id: string; title: string; stage: string }[];
  score: number;
  warm: boolean;
};

export async function fetchRelationships(): Promise<{ clusters: RelCluster[]; warm_intro_count: number }> {
  const res = await fetch("/api/relationships");
  if (!res.ok) throw new Error(`relationships failed: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Create `RelationshipsTab.tsx`**

`onOpen(oppId)` prop. Loads `fetchRelationships`. Header: "Relationships" + a line `{warm_intro_count} warm intros — companies where you know someone AND track a role`. Then a grid of **network cards** (`[grid-template-columns:repeat(auto-fill,minmax(340px,1fr))] gap-3.5`): each cluster is a card with the **company as the hub** — a centered company chip (`bg-panel text-white rounded-md`), and below it two labeled spoke groups:
  - **Contacts** (warm intros): each as an accent chip (`bg-accent-tint text-accent`) showing name + role.
  - **Roles**: each as a clickable chip (`border-line bg-surface-alt`, on click → `onOpen(opp.id)`) showing title + a small stage tag.
  Highlight warm clusters (both present) with an `border-accent` ring and a "⚡ warm intro" badge. Sort is already done server-side. `FetchError` on failure; Job Hunter tokens; no graph lib — a clean hub/spoke flex layout. Empty-state text when no clusters.

- [ ] **Step 3: Wire into shell**

- `page.tsx`: add `| "relationships"` to the union; import RelationshipsTab; render branch `) : canvasTab === "relationships" ? ( <RelationshipsTab onOpen={(id) => { setSelectedOpp(id); setCanvasTab("detail"); }} /> )`.
- `IconRail.tsx`: add `{ key: "relationships", label: "Relationships", icon: I("M5 6.2a2.2 2.2 0 100-4.4 2.2 2.2 0 000 4.4z M16 6.2a2.2 2.2 0 100-4.4 2.2 2.2 0 000 4.4z M10.5 17.7a2.2 2.2 0 100-4.4 2.2 2.2 0 000 4.4z M7 6.5h7M6.2 7.7l3.2 5.8M15.2 7.8l-3.4 5.7") }` (after "metrics" or "automations").

- [ ] **Step 4: Build** — `npm --prefix frontend install` then `npm --prefix frontend run build` → succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/app/components/RelationshipsTab.tsx frontend/app/page.tsx frontend/app/components/IconRail.tsx
git commit -m "feat(ui): Relationships network screen (company hubs, warm intros, roles)"
```
