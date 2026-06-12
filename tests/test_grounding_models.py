from __future__ import annotations

from sqlmodel import Session

from app.db import _ensure_column, engine
from app.models import Artifact, GroundingReport, ReviewStatus


def test_new_artifact_defaults_to_draft():
    with Session(engine) as s:
        a = Artifact(title="cv draft")
        s.add(a)
        s.commit()
        s.refresh(a)
    assert a.review_status == ReviewStatus.draft


def test_grounding_report_roundtrip():
    with Session(engine) as s:
        a = Artifact(title="cv draft")
        s.add(a)
        s.commit()
        s.refresh(a)
        r = GroundingReport(
            artifact_id=a.id, body_hash="abc", threshold=0.4,
            embedding_model="fake",
            findings=[{"text": "x", "start": 0, "end": 1, "score": 0.9,
                       "chunk_id": 1, "document_title": "d", "supported": True}],
            checked_count=1, unsupported_count=0,
        )
        s.add(r)
        s.commit()
        s.refresh(r)
    assert r.id is not None
    assert r.findings[0]["supported"] is True


def test_ensure_column_adds_and_is_idempotent(tmp_path):
    from sqlmodel import create_engine

    scratch = create_engine(f"sqlite:///{tmp_path}/scratch.db")
    with scratch.connect() as conn:
        conn.exec_driver_sql("CREATE TABLE artifacts (id INTEGER PRIMARY KEY, title VARCHAR)")
        conn.commit()
    _ensure_column(scratch, "artifacts", "review_status", "VARCHAR DEFAULT 'draft'")
    _ensure_column(scratch, "artifacts", "review_status", "VARCHAR DEFAULT 'draft'")  # no-op
    with scratch.connect() as conn:
        cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(artifacts)")]
    assert "review_status" in cols
