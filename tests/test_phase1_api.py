"""Phase 1 API flow: create -> stage -> action -> attention -> board -> artifact."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _past_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat()


def test_full_pipeline_flow(client):
    # create
    r = client.post(
        "/api/opportunities",
        json={"type": "job", "title": "API Flow Eng", "organization": "Flowco", "details": {"salary": "180k"}},
    )
    assert r.status_code == 200
    opp = r.json()
    oid = opp["id"]
    assert opp["stage"] == "new" and opp["type"] == "job"

    # list (filtered)
    listed = client.get("/api/opportunities?type=job").json()
    assert any(o["id"] == oid for o in listed)

    # advance stage
    r = client.patch(f"/api/opportunities/{oid}/stage", json={"stage": "active", "rationale": "applied"})
    assert r.status_code == 200 and r.json()["stage"] == "active"

    # add an overdue action
    r = client.post(
        "/api/actions",
        json={"title": "Chase recruiter", "opportunity_id": oid, "kind": "followup", "due_at": _past_iso(3)},
    )
    assert r.status_code == 200
    action_id = r.json()["id"]

    # attention surfaces the overdue action
    attn = client.get("/api/attention").json()
    assert attn["counts"]["overdue_actions"] >= 1
    assert any(i.get("action_id") == action_id for i in attn["items"])

    # complete it
    assert client.post(f"/api/actions/{action_id}/complete").json()["status"] == "done"

    # board groups it under 'active'
    board = client.get("/api/pipeline?type=job").json()
    assert "active" in board["columns"]
    assert any(o["id"] == oid for o in board["by_stage"]["active"])

    # artifact
    r = client.post(
        "/api/artifacts",
        json={"title": "Cover letter", "body": "# Dear Flowco", "opportunity_id": oid, "kind": "cover_letter"},
    )
    assert r.status_code == 200 and r.json()["version"] == 1
    arts = client.get(f"/api/artifacts?opportunity_id={oid}").json()
    assert any(a["title"] == "Cover letter" for a in arts)

    # detail bundles related rows
    detail = client.get(f"/api/opportunities/{oid}").json()
    assert detail["opportunity"]["id"] == oid
    assert len(detail["artifacts"]) >= 1
    assert any(d["kind"] == "stage_change" for d in detail["decisions"])  # stage move logged


def test_unknown_opportunity_404(client):
    assert client.get("/api/opportunities/nope").status_code == 404
    assert client.patch("/api/opportunities/nope/stage", json={"stage": "won"}).status_code == 404
