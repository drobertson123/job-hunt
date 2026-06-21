from __future__ import annotations

import sqlalchemy as sa
from sqlmodel import Session

from app.db import _ensure_column, engine
from app.models import (
    Application,
    ApplicationStatus,
    Briefing,
    BriefingFactKey,
    CommChannel,
    CommDirection,
    Communication,
    Company,
    CompanySize,
    Contact,
    JobSource,
    JobSourceKind,
    Opportunity,
    OpportunityType,
)


def test_company_roundtrip_and_default_size():
    with Session(engine) as s:
        c = Company(name="Acme Corp", domain="acme.com", ats_vendor="Greenhouse")
        s.add(c)
        s.commit()
        s.refresh(c)
        assert c.id is not None and len(c.id) == 32
        assert c.size == CompanySize.unknown
        assert c.domain == "acme.com" and c.details == {}


def test_jobsource_roundtrip_and_default_kind():
    with Session(engine) as s:
        js = JobSource(name="LinkedIn", url="https://linkedin.com/jobs",
                       saved_query="staff ml engineer remote")
        s.add(js)
        s.commit()
        s.refresh(js)
        assert js.id is not None and js.kind == JobSourceKind.other
        assert js.saved_query == "staff ml engineer remote"
        assert js.last_checked_at is None


def test_application_requires_opportunity_and_defaults_draft():
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Staff ML Engineer")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        app_row = Application(opportunity_id=opp.id,
                              portal_url="https://boards.greenhouse.io/x")
        s.add(app_row)
        s.commit()
        s.refresh(app_row)
        assert app_row.id is not None
        assert app_row.opportunity_id == opp.id
        assert app_row.status == ApplicationStatus.draft
        assert app_row.details == {} and app_row.submitted_at is None


def test_communication_log_roundtrip():
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role X")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        msg = Communication(
            opportunity_id=opp.id,
            direction=CommDirection.inbound,
            channel=CommChannel.sms,
            subject="Re: interview",
            body="Can you do Tuesday?",
        )
        s.add(msg)
        s.commit()
        s.refresh(msg)
        assert msg.id is not None
        assert msg.channel == CommChannel.sms and msg.direction == CommDirection.inbound
        assert msg.occurred_at is not None and msg.follow_up_due_at is None


def test_briefing_facts_roundtrip():
    with Session(engine) as s:
        opp = Opportunity(type=OpportunityType.job, title="Role Y")
        s.add(opp)
        s.commit()
        s.refresh(opp)
        b = Briefing(
            opportunity_id=opp.id,
            summary="Strong fit; remote-first.",
            facts=[
                {"key": BriefingFactKey.salary_range.value, "question": "Salary range?",
                 "answer": "$180-220k", "confidence": 0.7, "source": "levels.fyi"},
                {"key": BriefingFactKey.other.value, "question": "Visa sponsorship?",
                 "answer": "Yes", "confidence": None, "source": None},
            ],
        )
        s.add(b)
        s.commit()
        s.refresh(b)
        assert b.id is not None and len(b.facts) == 2
        assert b.facts[0]["key"] == "salary_range"
        assert b.company_id is None and b.source_hash is None


def test_opportunity_and_contact_fk_columns_roundtrip():
    with Session(engine) as s:
        co = Company(name="Globex")
        src = JobSource(name="Referral", kind=JobSourceKind.referral)
        s.add(co)
        s.add(src)
        s.commit()
        s.refresh(co)
        s.refresh(src)
        opp = Opportunity(type=OpportunityType.job, title="Role Z",
                          company_id=co.id, source_id=src.id)
        contact = Contact(name="Jane Recruiter", company_id=co.id)
        s.add(opp)
        s.add(contact)
        s.commit()
        s.refresh(opp)
        s.refresh(contact)
        assert opp.company_id == co.id and opp.source_id == src.id
        assert contact.company_id == co.id


def test_ensure_column_is_idempotent(tmp_path):
    eng = sa.create_engine(f"sqlite:///{tmp_path}/t.db")
    with eng.connect() as c:
        c.exec_driver_sql("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        c.commit()
    _ensure_column(eng, "t", "company_id", "VARCHAR")
    _ensure_column(eng, "t", "company_id", "VARCHAR")
    with eng.connect() as c:
        cols = [r[1] for r in c.exec_driver_sql("PRAGMA table_info(t)")]
    assert cols.count("company_id") == 1
