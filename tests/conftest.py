"""Test fixtures.

Point the app at an isolated temp DB *before* importing any app module (the
engine is created at import time from config). This keeps tests off the real
data/app.db.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Must run before `import app.*` anywhere.
_TMP = Path(tempfile.mkdtemp(prefix="oh-test-"))
os.environ["OH_DATA_DIR"] = str(_TMP / "data")
os.environ["OH_SESSIONS_DIR"] = str(_TMP / "sessions")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    init_db()
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_db():
    """Wipe per-test data: corpus, grounding, and the opportunity domain.

    Children before parents (FK order). Runs/Events/Notes/Settings are left
    alone — append-only logs and config that tests scope by id/key.
    """
    from sqlmodel import Session, delete

    from app.db import engine
    from app.models import (
        Action,
        Artifact,
        Chunk,
        Contact,
        Decision,
        Document,
        GroundingReport,
        Opportunity,
        Profile,
    )

    with Session(engine) as s:
        for model in (
            GroundingReport, Artifact, Action, Decision, Contact,
            Opportunity, Chunk, Document, Profile,
        ):
            s.exec(delete(model))
        s.commit()
    yield
