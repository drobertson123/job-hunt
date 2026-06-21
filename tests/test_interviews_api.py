def test_interview_crud_and_ics(client):
    # create
    r = client.post("/api/interviews", json={
        "title": "Tech screen", "starts_at": "2999-07-01T14:00:00",
        "kind": "technical", "location": "Zoom",
    })
    assert r.status_code == 200, r.text
    iv = r.json()
    iid = iv["id"]
    assert iv["kind"] == "technical"

    # list (upcoming)
    r = client.get("/api/interviews?upcoming=true")
    assert any(x["id"] == iid for x in r.json())

    # single .ics
    r = client.get(f"/api/interviews/{iid}.ics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    assert r.text.startswith("BEGIN:VCALENDAR")
    assert "BEGIN:VEVENT" in r.text

    # all-upcoming .ics
    r = client.get("/api/interviews/calendar.ics")
    assert r.status_code == 200
    assert "BEGIN:VCALENDAR" in r.text

    # delete
    assert client.delete(f"/api/interviews/{iid}").status_code == 204
    assert client.delete(f"/api/interviews/{iid}").status_code == 404


def test_interview_ics_unknown_404(client):
    assert client.get("/api/interviews/999999.ics").status_code == 404
