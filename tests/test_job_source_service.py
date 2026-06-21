from __future__ import annotations

from sqlmodel import Session

from app import services
from app.db import engine
from app.models import JobSource, JobSourceKind, Opportunity, OpportunityType


def test_upsert_job_source_creates_then_matches_case_insensitive():
    with Session(engine) as s:
        a = services.upsert_job_source(s, name="LinkedIn", kind=JobSourceKind.job_board)
        b = services.upsert_job_source(s, name="linkedin", url="https://linkedin.com")
        assert a.id == b.id  # case-insensitive name match
        assert b.kind == JobSourceKind.job_board  # not wiped
        assert b.url == "https://linkedin.com"


def test_upsert_job_source_links_opportunity():
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        js = services.upsert_job_source(s, name="Referral", kind=JobSourceKind.referral,
                                        link_opportunity_id=opp.id)
        s.refresh(opp)
        assert opp.source_id == js.id


def test_upsert_job_source_link_missing_opp_is_noop():
    with Session(engine) as s:
        js = services.upsert_job_source(s, name="Indeed", link_opportunity_id="nope")
        assert js.id is not None  # did not raise


def test_list_job_sources_ordered():
    with Session(engine) as s:
        services.upsert_job_source(s, name="Zip")
        services.upsert_job_source(s, name=" angel")
        names = [j.name for j in services.list_job_sources(s)]
        assert names == ["angel", "Zip"]
