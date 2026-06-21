from app.config import get_config


def test_sms_webhook_creates_inbound_communication(client):
    r = client.post(
        "/api/communications/sms",
        json={"from": "+15551234567", "body": "Hi, are you free Tue for a call?"},
    )
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["channel"] == "sms"
    assert c["direction"] == "inbound"
    assert c["thread_key"] == "+15551234567"
    assert "free Tue" in c["body"]

    # it shows up in the communications list
    assert any(x["id"] == c["id"] for x in client.get("/api/communications").json())


def test_sms_webhook_token_enforced_when_set(client, monkeypatch):
    monkeypatch.setattr(get_config(), "sms_webhook_token", "s3cret", raising=False)
    # missing/wrong token → 401
    assert client.post(
        "/api/communications/sms", json={"from": "+1", "body": "x"}
    ).status_code == 401
    assert client.post(
        "/api/communications/sms?token=nope", json={"from": "+1", "body": "x"}
    ).status_code == 401
    # correct token via query
    assert client.post(
        "/api/communications/sms?token=s3cret", json={"from": "+1", "body": "x"}
    ).status_code == 200
    # correct token via header
    assert client.post(
        "/api/communications/sms",
        json={"from": "+1", "body": "x"},
        headers={"X-SMS-Token": "s3cret"},
    ).status_code == 200


def test_sms_webhook_converts_offset_timestamp_to_utc(client):
    # +05:00 local time → stored as naive UTC (05:00 earlier), not truncated
    r = client.post(
        "/api/communications/sms",
        json={"from": "+1", "body": "x", "received_at": "2026-06-21T10:00:00+05:00"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["occurred_at"].startswith("2026-06-21T05:00:00")
