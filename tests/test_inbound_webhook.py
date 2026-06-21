def test_inbound_whatsapp_message(client):
    r = client.post(
        "/api/communications/inbound",
        json={"from": "Sarah (KORE1)", "body": "Sent you the JD on WhatsApp", "channel": "whatsapp"},
    )
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["channel"] == "whatsapp"
    assert c["direction"] == "inbound"
    assert c["thread_key"] == "Sarah (KORE1)"


def test_inbound_linkedin_message(client):
    r = client.post(
        "/api/communications/inbound",
        json={"from": "recruiter", "body": "Are you open to a chat?", "channel": "linkedin"},
    )
    assert r.status_code == 200
    assert r.json()["channel"] == "linkedin"


def test_inbound_defaults_to_other_and_rejects_bad_channel(client):
    ok = client.post("/api/communications/inbound", json={"from": "x", "body": "y"})
    assert ok.status_code == 200 and ok.json()["channel"] == "other"
    bad = client.post(
        "/api/communications/inbound",
        json={"from": "x", "body": "y", "channel": "carrier-pigeon"},
    )
    assert bad.status_code == 422  # not a valid CommChannel


def test_inbound_token_enforced_when_set(client, monkeypatch):
    from app.config import get_config

    monkeypatch.setattr(get_config(), "sms_webhook_token", "k", raising=False)
    assert client.post(
        "/api/communications/inbound", json={"from": "x", "body": "y"}
    ).status_code == 401
    assert client.post(
        "/api/communications/inbound",
        json={"from": "x", "body": "y"},
        headers={"X-SMS-Token": "k"},
    ).status_code == 200


def test_sms_endpoint_still_works(client):
    r = client.post("/api/communications/sms", json={"from": "+1", "body": "hi"})
    assert r.status_code == 200 and r.json()["channel"] == "sms"
