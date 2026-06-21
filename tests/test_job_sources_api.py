def test_job_source_create_patch_and_run(client, monkeypatch):
    # create
    r = client.post("/api/job-sources", json={
        "name": "LinkedIn ML", "kind": "job_board",
        "saved_query": "ml engineer remote", "auto_search": False,
    })
    assert r.status_code == 200, r.text
    sid = r.json()["id"]

    # patch: opt in
    r = client.patch(f"/api/job-sources/{sid}", json={"auto_search": True})
    assert r.status_code == 200
    assert r.json()["auto_search"] is True

    # run now (stub the agent runner so no web/CLI is hit)
    import app.routers.job_sources as mod

    async def fake_run_source_search(source_id, **kw):
        return {"source_id": source_id, "status": "ran"}

    monkeypatch.setattr(mod, "run_source_search", fake_run_source_search)
    r = client.post(f"/api/job-sources/{sid}/search")
    assert r.status_code == 200
    assert r.json()["status"] == "ran"

    # unknown id → 404
    assert client.patch("/api/job-sources/nope", json={"auto_search": True}).status_code == 404
    assert client.post("/api/job-sources/nope/search").status_code == 404
