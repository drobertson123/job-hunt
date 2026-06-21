from sqlmodel import Session, select

from app.db import engine
from app import gcontacts_service as gco, services
from app.models import Contact


def _import_request(people):
    def req(method, url, access_token, *, json=None, params=None):
        return {"connections": people}
    return req


def test_import_contacts_upserts_and_dedupes():
    people = [
        {"resourceName": "people/c1", "names": [{"displayName": "Sarah Lee"}],
         "emailAddresses": [{"value": "sarah@kore1.com"}],
         "organizations": [{"name": "KORE1"}]},
        {"resourceName": "people/c2", "names": [{"displayName": "No Email"}]},
        {"resourceName": "people/c3"},  # no name → skipped
    ]
    with Session(engine) as s:
        r1 = gco.import_contacts(s, access_token="AT", request=_import_request(people))
        assert r1 == {"imported": 2, "skipped": 1}
        rows = s.exec(select(Contact)).all()
        sarah = next(c for c in rows if c.name == "Sarah Lee")
        assert sarah.email == "sarah@kore1.com" and sarah.organization == "KORE1"
        assert sarah.google_resource_name == "people/c1"
        # re-import dedupes on resourceName
        r2 = gco.import_contacts(s, access_token="AT", request=_import_request(people))
        assert r2["imported"] == 0


def test_push_contact_creates_then_updates():
    log = []

    def req(method, url, access_token, *, json=None, params=None):
        log.append((method, url))
        if method == "POST":
            return {"resourceName": "people/new1"}
        return {}

    with Session(engine) as s:
        c = services.add_contact(s, name="Bob Roe", email="bob@x.com", organization="Acme")
        rn = gco.push_contact(s, c, access_token="AT", request=req)
        assert rn == "people/new1" and c.google_resource_name == "people/new1"
        assert log[0][0] == "POST"
        log2_len = len(log)
        gco.push_contact(s, c, access_token="AT", request=req)  # linked → PATCH
        assert log[log2_len][0] == "PATCH"
