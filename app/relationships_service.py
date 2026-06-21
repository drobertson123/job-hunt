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
