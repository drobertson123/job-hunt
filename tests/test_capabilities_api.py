from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import OpportunityType


def _seed_opportunity() -> str:
    with Session(engine) as s:
        opp = services.upsert_opportunity(
            s, type=OpportunityType.job, title="Staff ML Engineer",
            dedupe_key="cap-test", organization="Acme AI", url=None,
            location=None, summary="PyTorch platform team", source="manual",
            details={},
        )
        return opp.id


def _fake_stream(captured: dict):
    async def fake_stream_run(prompt, *, model=None, api_key=None):  # noqa: ARG001
        captured["prompt"] = prompt
        yield {"run_id": "r1", "seq": 0, "type": "status", "content": "running"}
        yield {"run_id": "r1", "seq": 1, "type": "result", "content": "{}"}

    return fake_stream_run


def test_list_capabilities(client):
    r = client.get("/api/capabilities")
    assert r.status_code == 200
    by_name = {c["name"]: c for c in r.json()}
    assert set(by_name) == {
        "enrich-opportunity", "company-research", "cv-tailor",
        "interview-prep", "fit-analysis",
    }
    assert by_name["fit-analysis"]["requires_opportunity"] is True
    assert by_name["enrich-opportunity"]["requires_input"] is True


def test_invoke_unknown_capability_404(client):
    assert client.post("/api/capabilities/nope", json={}).status_code == 404


def test_invoke_missing_opportunity_id_422(client):
    assert client.post("/api/capabilities/fit-analysis", json={}).status_code == 422


def test_invoke_unknown_opportunity_404(client):
    r = client.post(
        "/api/capabilities/fit-analysis", json={"opportunity_id": "missing"}
    )
    assert r.status_code == 404


def test_invoke_missing_required_input_422(client):
    assert client.post("/api/capabilities/enrich-opportunity", json={}).status_code == 422


def test_invoke_streams_templated_prompt(client, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        "app.routers.capabilities.stream_run", _fake_stream(captured)
    )
    opp_id = _seed_opportunity()
    r = client.post("/api/capabilities/fit-analysis", json={"opportunity_id": opp_id})
    assert r.status_code == 200
    assert "career-pack:fit-analysis" in captured["prompt"]
    assert "Acme AI" in captured["prompt"]
    assert opp_id in captured["prompt"]
    # SSE frames made it to the body
    assert '"type": "status"' in r.text
    assert '"type": "result"' in r.text


def test_invoke_enrich_passes_input(client, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        "app.routers.capabilities.stream_run", _fake_stream(captured)
    )
    r = client.post(
        "/api/capabilities/enrich-opportunity",
        json={"input": "We are hiring a Platform Engineer in Berlin."},
    )
    assert r.status_code == 200
    assert "Platform Engineer" in captured["prompt"]
