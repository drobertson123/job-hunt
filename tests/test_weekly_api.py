def test_weekly_review_endpoint_shape(client):
    r = client.get("/api/weekly-review")
    assert r.status_code == 200
    body = r.json()
    for key in ("to_identify", "to_apply", "to_follow_up", "interviews_this_week", "counts"):
        assert key in body


def test_create_weekly_actions_endpoint(client):
    r = client.post("/api/weekly-review/actions")
    assert r.status_code == 200
    assert "created" in r.json()
