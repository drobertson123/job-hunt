from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import (
    Company,
    CompanySize,
    Contact,
    Opportunity,
    OpportunityType,
)


def test_upsert_company_creates_then_matches_case_insensitive():
    with Session(engine) as s:
        a = services.upsert_company(s, name="Acme Corp", industry="Energy")
        b = services.upsert_company(s, name="acme corp", ats_vendor="Greenhouse")
        assert a.id == b.id  # case-insensitive name match → same row
        assert b.industry == "Energy"  # incremental: not wiped by the second call
        assert b.ats_vendor == "Greenhouse"
        assert b.size == CompanySize.unknown


def test_upsert_company_update_by_id_is_incremental():
    with Session(engine) as s:
        a = services.upsert_company(s, name="Globex", domain="globex.com")
        updated = services.upsert_company(s, name="Globex", company_id=a.id,
                                          industry="Manufacturing")
        assert updated.id == a.id
        assert updated.domain == "globex.com"  # untouched
        assert updated.industry == "Manufacturing"


def test_list_companies_ordered():
    with Session(engine) as s:
        services.upsert_company(s, name="Zeta")
        services.upsert_company(s, name="alpha")
        names = [c.name for c in services.list_companies(s)]
        assert names == ["alpha", "Zeta"]  # case-insensitive order


def test_backfill_links_opps_and_contacts_idempotently():
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role", organization="Initech")
        ct = Contact(name="Jane", organization="Initech")
        blank = Opportunity(type=OpportunityType.job, title="No org")  # organization None
        s.add(opp)
        s.add(ct)
        s.add(blank)
        s.commit()
        s.refresh(opp)
        s.refresh(ct)
        s.refresh(blank)

        result = services.backfill_company_ids(s)
        assert result["opportunities_linked"] == 1
        assert result["contacts_linked"] == 1
        s.refresh(opp)
        s.refresh(ct)
        s.refresh(blank)
        assert opp.company_id is not None and ct.company_id == opp.company_id
        assert blank.company_id is None  # no organization → skipped

        again = services.backfill_company_ids(s)
        assert again["opportunities_linked"] == 0 and again["contacts_linked"] == 0
