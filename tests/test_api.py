"""API-level tests: health round-trip and settings (secrets never leaked)."""

from __future__ import annotations


def test_health_round_trip(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "notes" in body["db"] and "runs" in body["db"]
    assert "claude_cli" in body["agent"]


def test_settings_set_and_mask(client):
    r = client.put(
        "/api/settings",
        json={"anthropic_api_key": "sk-secret-123", "agent_model": "claude-sonnet-4-6"},
    )
    assert r.status_code == 200
    view = r.json()
    assert view["anthropic_key_configured"] is True
    assert view["agent_model"] == "claude-sonnet-4-6"
    # The secret itself must never appear in the response.
    assert "sk-secret-123" not in r.text

    r2 = client.get("/api/settings")
    assert r2.json()["anthropic_key_configured"] is True
    assert "sk-secret-123" not in r2.text
