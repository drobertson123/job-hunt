# Grounding / Anti-Fabrication + Review Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `grounding_service` — sentence-level embedding-similarity verification of artifact text against the corpus, producing a structured report + `[MISSING]`-annotated text — plus an Artifact review lifecycle (`draft → needs_review → approved`) with HTTP endpoints.

**Architecture:** A deterministic markdown-aware sentence splitter produces offset-exact spans; all sentences are embedded in one batch through the **injectable** `Embedder` from slice B and cosine-scored against all corpus chunks (same numpy routine as `corpus_service.search`, batched as one matmul). Below `grounding_min_similarity` = unsupported → `[MISSING]`. Reports persist in a `grounding_reports` table (one replaceable row per artifact, with a `body_hash` for staleness detection); the stored artifact body is never mutated — annotation is derived. **No LLM in the verify path → the entire slice tests offline; no live gate.**

**Tech Stack:** Python 3.12, SQLModel/SQLite, FastAPI, numpy, pytest (+ pytest-asyncio `asyncio_mode=auto`). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-11-grounding-review-gate-design.md`

**Conventions to follow (already in the codebase):**
- Models in `app/models.py`: naive-UTC `_utcnow()`, JSON via `Field(default_factory=..., sa_column=Column(JSON))`, int autoincrement PKs (see `Artifact`).
- Routers: prefix `/api/<name>`, `Depends(get_session)`; grounding endpoints extend the existing `app/routers/artifacts.py`.
- Embedder injection seam: routers define a module-level `_<x>_embedder(session)` indirection that tests monkeypatch (see `app/routers/corpus.py:_embedder_for`).
- Tests use deterministic fake embedders (lexical vocab-count vectors); the autouse `_clear_corpus` fixture in `tests/conftest.py` wipes corpus tables per test.
- Offline test command: `.venv/bin/python -m pytest` (NOT plain `uv run`, which re-resolves over the network). **Never pipe pytest through `tail` before `&&` — it masks the exit code.**
- Artifacts are append-only versioned: `services.add_artifact` auto-increments `version` for same opp+kind+title and always creates a NEW row — so a new version naturally starts at `draft`.

**Known limitation (by design, documented in the spec):** cosine similarity measures topical closeness, not entailment. The verifier is a review aid; human approval is the authority. Do not "fix" this with an LLM judge — that was explicitly not chosen.

---

### Task 1: Config — `grounding_min_similarity`

**Files:**
- Modify: `app/config.py:42-48` (LLM models block)
- Test: `tests/test_grounding_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grounding_config.py
from __future__ import annotations

from app.config import AppConfig, get_config


def test_grounding_min_similarity_default():
    assert get_config().grounding_min_similarity == 0.40


def test_grounding_min_similarity_env_override(monkeypatch):
    # Fresh AppConfig (not the lru-cached get_config) to test env wiring.
    monkeypatch.setenv("OH_GROUNDING_MIN_SIMILARITY", "0.85")
    assert AppConfig().grounding_min_similarity == 0.85
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_grounding_config.py -v`
Expected: FAIL — `AttributeError: 'AppConfig' object has no attribute 'grounding_min_similarity'`

- [ ] **Step 3: Add the config field**

In `app/config.py`, immediately after the `embedding_model` line (line 48), add:

```python
    # Grounding verifier: sentences scoring below this cosine similarity vs the
    # corpus are marked [MISSING]. Conservative default; tune from real runs
    # (the report stores raw scores and the threshold used per run).
    grounding_min_similarity: float = 0.40
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_grounding_config.py -v; echo "EXIT=$?"`
Expected: 2 passed, EXIT=0

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_grounding_config.py
git commit -m "feat(grounding): add grounding_min_similarity config (default 0.40)"
```

---

### Task 2: Models + migration — `ReviewStatus`, `Artifact.review_status`, `GroundingReport`

**Files:**
- Modify: `app/models.py` (Artifact class ~line 212; new section at end of file)
- Modify: `app/db.py:20-24` (`init_db`)
- Modify: `tests/conftest.py:37-48` (`_clear_corpus`)
- Test: `tests/test_grounding_models.py`

`SQLModel.metadata.create_all` never adds columns to an existing table, so the real
`data/app.db` (which already has `artifacts`) needs an idempotent `ALTER TABLE` guard.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grounding_models.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_grounding_models.py -v`
Expected: FAIL — `ImportError: cannot import name '_ensure_column'` (and `ReviewStatus`/`GroundingReport`)

- [ ] **Step 3: Add the models**

In `app/models.py`, add `ReviewStatus` immediately BEFORE the `Artifact` class (after `ArtifactFormat`, ~line 210):

```python
class ReviewStatus(str, Enum):
    """Review-before-send gate: grounding check -> needs_review -> human approval."""

    draft = "draft"
    needs_review = "needs_review"
    approved = "approved"
```

In the `Artifact` class, add after the `version: int = 1` line:

```python
    review_status: ReviewStatus = Field(default=ReviewStatus.draft, index=True)
```

At the END of `app/models.py`, add:

```python
# --------------------------------------------------------------------------- #
# Phase 2 slice C: grounding reports (anti-fabrication verifier output).
# --------------------------------------------------------------------------- #


class GroundingReport(SQLModel, table=True):
    """One current grounding report per artifact (replaced on re-check).

    `body_hash` is sha256 of the artifact body that was checked; a mismatch vs
    the current body means the report is stale. Annotated text is derived from
    body + findings offsets, never stored.
    """

    __tablename__ = "grounding_reports"

    id: int | None = Field(default=None, primary_key=True)
    artifact_id: int = Field(foreign_key="artifacts.id", index=True, unique=True)
    body_hash: str
    threshold: float
    embedding_model: str = ""
    # Per sentence: {text, start, end, score, chunk_id|None,
    #               document_title|None, supported}
    findings: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    checked_count: int = 0
    unsupported_count: int = 0
    created_at: datetime = Field(default_factory=_utcnow)
```

Also update the module docstring line `Phase 2 adds: ...` to read:

```python
Phase 2 adds: corpus_documents, corpus_chunks, profile, grounding_reports
(+ Artifact.review_status).
```

- [ ] **Step 4: Add the migration guard in `app/db.py`**

Replace `init_db` with:

```python
def _ensure_column(target_engine, table: str, column: str, ddl: str) -> None:
    """Idempotent ALTER TABLE guard: create_all never adds columns to existing tables."""
    with target_engine.connect() as conn:
        cols = [row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")]
        if column not in cols:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            conn.commit()


def init_db() -> None:
    """Create tables. Import models for side-effect registration first."""
    from app import models  # noqa: F401  (registers tables on SQLModel.metadata)

    SQLModel.metadata.create_all(engine)
    # Slice C: pre-existing DBs have artifacts without review_status.
    _ensure_column(engine, "artifacts", "review_status", "VARCHAR DEFAULT 'draft'")
```

- [ ] **Step 5: Extend the autouse clear fixture**

In `tests/conftest.py`, replace the `_clear_corpus` fixture body's import + loop:

```python
@pytest.fixture(autouse=True)
def _clear_corpus():
    from sqlmodel import Session, delete

    from app.db import engine
    from app.models import Artifact, Chunk, Document, GroundingReport, Profile

    with Session(engine) as s:
        # GroundingReport before Artifact (FK); corpus tables independent.
        for model in (GroundingReport, Artifact, Chunk, Document, Profile):
            s.exec(delete(model))
        s.commit()
    yield
```

- [ ] **Step 6: Run the new tests, then the FULL suite (fixture change touches everything)**

Run: `.venv/bin/python -m pytest tests/test_grounding_models.py -v; echo "EXIT=$?"`
Expected: 3 passed, EXIT=0

Run: `.venv/bin/python -m pytest; echo "EXIT=$?"`
Expected: all pass (49+ passed, 2 skipped), EXIT=0. If an existing test fails, it was
relying on artifacts leaking across tests — fix THAT test to create its own data.

- [ ] **Step 7: Commit**

```bash
git add app/models.py app/db.py tests/conftest.py tests/test_grounding_models.py
git commit -m "feat(grounding): ReviewStatus + Artifact.review_status + grounding_reports table (with idempotent column migration)"
```

---

### Task 3: `split_sentences` — deterministic markdown-aware splitter

**Files:**
- Create: `app/grounding_service.py`
- Test: `tests/test_grounding_split.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_grounding_split.py
from __future__ import annotations

from app.grounding_service import Span, split_sentences


def test_offsets_are_exact():
    text = "I built APIs in Python. I led a team of five engineers."
    spans = split_sentences(text)
    assert [s.text for s in spans] == [
        "I built APIs in Python.",
        "I led a team of five engineers.",
    ]
    for s in spans:
        assert text[s.start:s.end] == s.text


def test_markdown_structure_headings_and_bullets():
    text = "## Experience\n- Built scalable APIs in Python at Acme.\n\nLed major data migrations safely."
    spans = split_sentences(text)
    # Bare heading "Experience" is < 3 words -> dropped; bullet marker excluded
    # from the span; offsets still index into the ORIGINAL text.
    assert [s.text for s in spans] == [
        "Built scalable APIs in Python at Acme.",
        "Led major data migrations safely.",
    ]
    for s in spans:
        assert text[s.start:s.end] == s.text


def test_abbreviations_do_not_split():
    text = "I used many tools, e.g. Python and Go, every day."
    spans = split_sentences(text)
    assert len(spans) == 1
    assert spans[0].text == text


def test_short_spans_are_skipped():
    # Signatures / closings / bare headings: degenerate-input guard.
    text = "Sincerely,\nJane Doe\n\nI delivered the project on time."
    spans = split_sentences(text)
    assert [s.text for s in spans] == ["I delivered the project on time."]


def test_numbers_with_periods_do_not_split():
    text = "I improved latency by 3.5 times in one quarter."
    spans = split_sentences(text)
    assert len(spans) == 1


def test_empty_text_yields_no_spans():
    assert split_sentences("") == []
    assert split_sentences("\n\n  \n") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_grounding_split.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.grounding_service'`

- [ ] **Step 3: Create `app/grounding_service.py` with the splitter**

```python
# app/grounding_service.py
"""Grounding verifier: flag artifact sentences unsupported by the corpus.

Embedding-similarity threshold check — NO LLM in the verify path. Each
sentence is embedded (injectable Embedder, same type as corpus_service) and
cosine-matched against all corpus chunks; best score below
``grounding_min_similarity`` -> unsupported -> ``[MISSING]``.

Cosine measures topical closeness, not entailment: this is a review aid that
surfaces low-support spans, not a truth oracle. The human approval step
(`approve_artifact`) is the authority.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass

import numpy as np
from sqlmodel import Session, select

from app.config import get_config
from app.corpus_service import Embedder
from app.models import (
    Artifact,
    Chunk,
    Document,
    GroundingReport,
    ReviewStatus,
    _utcnow,
)


class InvalidStatusTransition(Exception):
    """Raised when an artifact review-status transition is not allowed."""


@dataclass
class Span:
    """A sentence with exact char offsets into the original text."""

    text: str
    start: int
    end: int


# Markdown line prefixes excluded from spans: headings, bullets, numbered
# items, blockquotes. Offsets still index into the original text.
_LINE_PREFIX = re.compile(r"^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s+)?")
# Sentence end: ./!/? followed by whitespace or end-of-line. "3.5" has no
# trailing space after the dot, so decimals never match.
_SENT_END = re.compile(r"[.!?](?=\s|$)")
_ABBREVIATIONS = (
    "e.g.", "i.e.", "etc.", "vs.", "Mr.", "Ms.", "Dr.",
    "Jr.", "Sr.", "Inc.", "Co.", "St.", "No.",
)
# Spans under this many words are skipped (signatures, "Sincerely,", bare
# headings) — a degenerate-input guard, NOT a factual filter (spec decision 3).
_MIN_WORDS = 3


def split_sentences(text: str) -> list[Span]:
    """Deterministic markdown-aware sentence splitter with exact offsets."""
    spans: list[Span] = []
    offset = 0
    for line in text.split("\n"):
        prefix_len = _LINE_PREFIX.match(line).end()
        content = line[prefix_len:]
        base = offset + prefix_len
        seg_start = 0
        for m in _SENT_END.finditer(content):
            if any(content[: m.end()].endswith(a) for a in _ABBREVIATIONS):
                continue
            _emit(spans, base + seg_start, content[seg_start : m.end()])
            seg_start = m.end()
        _emit(spans, base + seg_start, content[seg_start:])
        offset += len(line) + 1  # +1 for the split-away "\n"
    return spans


def _emit(spans: list[Span], start: int, piece: str) -> None:
    stripped = piece.strip()
    if len(stripped.split()) < _MIN_WORDS:
        return
    lead = len(piece) - len(piece.lstrip())
    s = start + lead
    spans.append(Span(text=stripped, start=s, end=s + len(stripped)))
```

(The imports beyond `re`/`dataclass` are used by Tasks 4–6; keeping them now avoids
churn. If the linter complains about unused imports at this step, that is expected
and resolves in Task 4.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_grounding_split.py -v; echo "EXIT=$?"`
Expected: 6 passed, EXIT=0

- [ ] **Step 5: Commit**

```bash
git add app/grounding_service.py tests/test_grounding_split.py
git commit -m "feat(grounding): deterministic markdown-aware sentence splitter with exact offsets"
```

---

### Task 4: `check_grounding` — batched cosine scoring vs the corpus

**Files:**
- Modify: `app/grounding_service.py` (append)
- Test: `tests/test_grounding_check.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_grounding_check.py
from __future__ import annotations

import pytest
from sqlmodel import Session

from app.corpus_service import ingest_document
from app.db import engine
from app.grounding_service import check_grounding
from app.models import DocumentMediaType, DocumentSource

# Deterministic embedder: vocab word-count vectors. Sentences sharing corpus
# vocabulary score high; off-corpus sentences embed to ~zero -> score ~0.
_VOCAB = ["python", "kubernetes", "leadership", "apis"]


def _lexical_embedder(texts):
    return [[float(t.lower().count(w)) for w in _VOCAB] for t in texts]


def _seed_corpus(s: Session):
    ingest_document(
        s, title="resume.md", source_kind=DocumentSource.paste,
        media_type=DocumentMediaType.md,
        data=b"I build python apis and run kubernetes clusters with leadership.",
        embedder=_lexical_embedder,
    )


def test_supported_and_unsupported_sentences():
    text = "I build python apis every day. I won a Nobel prize in chemistry."
    with Session(engine) as s:
        _seed_corpus(s)
        result = check_grounding(s, text, embedder=_lexical_embedder, threshold=0.4)
    assert result.checked_count == 2
    by_text = {f.text: f for f in result.findings}
    supported = by_text["I build python apis every day."]
    fabricated = by_text["I won a Nobel prize in chemistry."]
    assert supported.supported is True
    assert supported.document_title == "resume.md"
    assert supported.chunk_id is not None
    assert fabricated.supported is False
    assert fabricated.score < 0.4
    assert result.unsupported_count == 1


def test_threshold_changes_classification():
    text = "I build python apis every day."
    with Session(engine) as s:
        _seed_corpus(s)
        lenient = check_grounding(s, text, embedder=_lexical_embedder, threshold=0.1)
        strict = check_grounding(s, text, embedder=_lexical_embedder, threshold=0.999)
    assert lenient.findings[0].supported is True
    assert strict.findings[0].supported is False


def test_default_threshold_comes_from_config():
    with Session(engine) as s:
        _seed_corpus(s)
        result = check_grounding(
            s, "I build python apis every day.", embedder=_lexical_embedder
        )
    assert result.threshold == 0.40  # config default from Task 1


def test_empty_corpus_raises():
    with Session(engine) as s:
        with pytest.raises(ValueError, match="corpus is empty"):
            check_grounding(s, "Any text at all here.", embedder=_lexical_embedder)


def test_no_checkable_sentences_yields_empty_findings():
    with Session(engine) as s:
        _seed_corpus(s)
        result = check_grounding(s, "Sincerely,", embedder=_lexical_embedder)
    assert result.findings == []
    assert result.checked_count == 0
    assert result.unsupported_count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_grounding_check.py -v`
Expected: FAIL — `ImportError: cannot import name 'check_grounding'`

- [ ] **Step 3: Append to `app/grounding_service.py`**

```python
@dataclass
class SentenceFinding:
    """One scored sentence; persisted as a dict in GroundingReport.findings."""

    text: str
    start: int
    end: int
    score: float
    chunk_id: int | None
    document_title: str | None
    supported: bool


@dataclass
class GroundingResult:
    findings: list[SentenceFinding]
    threshold: float
    embedding_model: str

    @property
    def checked_count(self) -> int:
        return len(self.findings)

    @property
    def unsupported_count(self) -> int:
        return sum(1 for f in self.findings if not f.supported)


def check_grounding(
    session: Session,
    text: str,
    *,
    embedder: Embedder,
    threshold: float | None = None,
) -> GroundingResult:
    """Score every sentence of `text` against the corpus by best cosine match.

    Raises ValueError on an empty corpus: checking against nothing would mark
    everything [MISSING], which is misleading rather than safe.

    Same single-embedding-model assumption as corpus_service.search(): all
    stored chunk vectors share one dimension.
    """
    if threshold is None:
        threshold = get_config().grounding_min_similarity
    rows = session.exec(select(Chunk)).all()
    if not rows:
        raise ValueError("corpus is empty — ingest documents before running a grounding check")

    model = rows[0].embedding_model
    spans = split_sentences(text)
    if not spans:
        return GroundingResult(findings=[], threshold=threshold, embedding_model=model)

    smat = np.asarray(embedder([s.text for s in spans]), dtype=np.float32)
    cmat = np.vstack([np.frombuffer(r.embedding, dtype=np.float32) for r in rows])
    sn = smat / (np.linalg.norm(smat, axis=1, keepdims=True) + 1e-12)
    cn = cmat / (np.linalg.norm(cmat, axis=1, keepdims=True) + 1e-12)
    scores = sn @ cn.T  # (n_sentences, n_chunks)
    best = np.argmax(scores, axis=1)

    titles = {d.id: d.title for d in session.exec(select(Document)).all()}
    findings: list[SentenceFinding] = []
    for i, span in enumerate(spans):
        ci = int(best[i])
        score = float(scores[i, ci])
        chunk = rows[ci]
        findings.append(SentenceFinding(
            text=span.text, start=span.start, end=span.end, score=score,
            chunk_id=chunk.id, document_title=titles.get(chunk.document_id),
            supported=score >= threshold,
        ))
    return GroundingResult(findings=findings, threshold=threshold, embedding_model=model)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_grounding_check.py -v; echo "EXIT=$?"`
Expected: 5 passed, EXIT=0

- [ ] **Step 5: Commit**

```bash
git add app/grounding_service.py tests/test_grounding_check.py
git commit -m "feat(grounding): check_grounding — batched cosine scoring of sentences vs corpus chunks"
```

---

### Task 5: `annotate` — derived `[MISSING]` markup (pure function)

**Files:**
- Modify: `app/grounding_service.py` (append)
- Test: `tests/test_grounding_annotate.py`

`annotate` operates on the PERSISTED form of findings (list of dicts), since the
router rebuilds annotated text from `GroundingReport.findings` JSON.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_grounding_annotate.py
from __future__ import annotations

from app.grounding_service import annotate


def _finding(text, start, end, supported):
    return {"text": text, "start": start, "end": end, "score": 0.0,
            "chunk_id": None, "document_title": None, "supported": supported}


def test_unsupported_sentences_get_missing_markers():
    text = "I build python apis. I won a Nobel prize."
    findings = [
        _finding("I build python apis.", 0, 20, True),
        _finding("I won a Nobel prize.", 21, 41, False),
    ]
    out = annotate(text, findings)
    assert out == "I build python apis. [MISSING: I won a Nobel prize.]"
    assert text == "I build python apis. I won a Nobel prize."  # original untouched


def test_multiple_unsupported_spans_applied_in_reverse_offset_order():
    text = "Alpha beta gamma. Delta epsilon zeta. Eta theta iota."
    findings = [
        _finding("Alpha beta gamma.", 0, 17, False),
        _finding("Delta epsilon zeta.", 18, 37, True),
        _finding("Eta theta iota.", 38, 53, False),
    ]
    out = annotate(text, findings)
    assert out == "[MISSING: Alpha beta gamma.] Delta epsilon zeta. [MISSING: Eta theta iota.]"


def test_all_supported_returns_text_unchanged():
    text = "Everything here is fine."
    findings = [_finding(text, 0, len(text), True)]
    assert annotate(text, findings) == text


def test_no_findings_returns_text_unchanged():
    assert annotate("Some text.", []) == "Some text."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_grounding_annotate.py -v`
Expected: FAIL — `ImportError: cannot import name 'annotate'`

- [ ] **Step 3: Append to `app/grounding_service.py`**

```python
def annotate(text: str, findings: list[dict]) -> str:
    """Return a copy of `text` with [MISSING: ...] wrapped around unsupported spans.

    Takes the persisted (dict) form of findings. Applies markers in reverse
    offset order so earlier offsets stay valid. Never mutates stored bodies —
    annotation is always derived.
    """
    out = text
    unsupported = [f for f in findings if not f["supported"]]
    for f in sorted(unsupported, key=lambda f: f["start"], reverse=True):
        out = out[: f["start"]] + f"[MISSING: {out[f['start']:f['end']]}]" + out[f["end"]:]
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_grounding_annotate.py -v; echo "EXIT=$?"`
Expected: 4 passed, EXIT=0

- [ ] **Step 5: Commit**

```bash
git add app/grounding_service.py tests/test_grounding_annotate.py
git commit -m "feat(grounding): annotate — derived [MISSING] markup from persisted findings"
```

---

### Task 6: Lifecycle — `run_grounding_check` + `approve_artifact`

**Files:**
- Modify: `app/grounding_service.py` (append)
- Test: `tests/test_grounding_lifecycle.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_grounding_lifecycle.py
from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app import services
from app.corpus_service import ingest_document
from app.db import engine
from app.grounding_service import (
    InvalidStatusTransition,
    approve_artifact,
    run_grounding_check,
)
from app.models import (
    Artifact,
    DocumentMediaType,
    DocumentSource,
    GroundingReport,
    ReviewStatus,
)

_VOCAB = ["python", "kubernetes", "leadership", "apis"]


def _lexical_embedder(texts):
    return [[float(t.lower().count(w)) for w in _VOCAB] for t in texts]


def _seed(s: Session) -> int:
    ingest_document(
        s, title="resume.md", source_kind=DocumentSource.paste,
        media_type=DocumentMediaType.md,
        data=b"I build python apis and run kubernetes clusters with leadership.",
        embedder=_lexical_embedder,
    )
    a = services.add_artifact(
        s, title="cover letter",
        body="I build python apis every day. I won a Nobel prize in chemistry.",
    )
    return a.id


def test_check_persists_report_and_sets_needs_review():
    with Session(engine) as s:
        aid = _seed(s)
        report = run_grounding_check(s, aid, embedder=_lexical_embedder)
        artifact = s.get(Artifact, aid)
    assert artifact.review_status == ReviewStatus.needs_review
    assert report.artifact_id == aid
    assert report.checked_count == 2
    assert report.unsupported_count == 1
    assert len(report.body_hash) == 64  # sha256 hex


def test_recheck_replaces_report_not_duplicates():
    with Session(engine) as s:
        aid = _seed(s)
        run_grounding_check(s, aid, embedder=_lexical_embedder)
        run_grounding_check(s, aid, embedder=_lexical_embedder)
        reports = s.exec(
            select(GroundingReport).where(GroundingReport.artifact_id == aid)
        ).all()
    assert len(reports) == 1


def test_approve_only_from_needs_review():
    with Session(engine) as s:
        aid = _seed(s)
        with pytest.raises(InvalidStatusTransition):
            approve_artifact(s, aid)  # still draft: unchecked -> cannot approve
        run_grounding_check(s, aid, embedder=_lexical_embedder)
        artifact = approve_artifact(s, aid)
        assert artifact.review_status == ReviewStatus.approved
        with pytest.raises(InvalidStatusTransition):
            approve_artifact(s, aid)  # already approved


def test_new_version_starts_at_draft():
    with Session(engine) as s:
        aid = _seed(s)
        run_grounding_check(s, aid, embedder=_lexical_embedder)
        approve_artifact(s, aid)
        v2 = services.add_artifact(s, title="cover letter", body="New body text here.")
    assert v2.version == 2
    assert v2.id != aid
    assert v2.review_status == ReviewStatus.draft


def test_check_missing_artifact_raises_lookup_error():
    with Session(engine) as s:
        with pytest.raises(LookupError):
            run_grounding_check(s, 999_999, embedder=_lexical_embedder)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_grounding_lifecycle.py -v`
Expected: FAIL — `ImportError: cannot import name 'run_grounding_check'`

- [ ] **Step 3: Append to `app/grounding_service.py`**

```python
def _body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def run_grounding_check(
    session: Session,
    artifact_id: int,
    *,
    embedder: Embedder,
    threshold: float | None = None,
) -> GroundingReport:
    """Check an artifact's body, persist the report (replacing any prior one),
    and move the artifact to needs_review."""
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise LookupError(f"artifact {artifact_id} not found")
    result = check_grounding(session, artifact.body, embedder=embedder, threshold=threshold)

    for old in session.exec(
        select(GroundingReport).where(GroundingReport.artifact_id == artifact_id)
    ).all():
        session.delete(old)

    report = GroundingReport(
        artifact_id=artifact_id,
        body_hash=_body_hash(artifact.body),
        threshold=result.threshold,
        embedding_model=result.embedding_model,
        findings=[asdict(f) for f in result.findings],
        checked_count=result.checked_count,
        unsupported_count=result.unsupported_count,
    )
    session.add(report)
    artifact.review_status = ReviewStatus.needs_review
    artifact.updated_at = _utcnow()
    session.add(artifact)
    session.commit()
    session.refresh(report)
    return report


def approve_artifact(session: Session, artifact_id: int) -> Artifact:
    """needs_review -> approved. Any other starting status is rejected:
    an unchecked draft cannot be approved — that IS the review gate."""
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise LookupError(f"artifact {artifact_id} not found")
    if artifact.review_status != ReviewStatus.needs_review:
        raise InvalidStatusTransition(
            f"cannot approve from status '{artifact.review_status.value}' — "
            "run a grounding check first"
        )
    artifact.review_status = ReviewStatus.approved
    artifact.updated_at = _utcnow()
    session.add(artifact)
    session.commit()
    session.refresh(artifact)
    return artifact
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_grounding_lifecycle.py -v; echo "EXIT=$?"`
Expected: 5 passed, EXIT=0

- [ ] **Step 5: Commit**

```bash
git add app/grounding_service.py tests/test_grounding_lifecycle.py
git commit -m "feat(grounding): run_grounding_check + approve_artifact review-gate lifecycle"
```

---

### Task 7: HTTP endpoints on the artifacts router

**Files:**
- Modify: `app/routers/artifacts.py`
- Test: `tests/test_grounding_api.py`

Three endpoints: `POST /api/artifacts/{id}/grounding` (run), `GET /api/artifacts/{id}/grounding`
(report + annotated text + stale flag), `POST /api/artifacts/{id}/approve`.
Same embedder-seam pattern as `app/routers/corpus.py:_embedder_for`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_grounding_api.py
from __future__ import annotations

import pytest
from sqlmodel import Session

from app import services
from app.corpus_service import ingest_document
from app.db import engine
from app.models import Artifact, DocumentMediaType, DocumentSource

_VOCAB = ["python", "kubernetes", "leadership", "apis"]


def _lexical_embedder(texts):
    return [[float(t.lower().count(w)) for w in _VOCAB] for t in texts]


@pytest.fixture
def fake_embedder(monkeypatch):
    monkeypatch.setattr(
        "app.routers.artifacts._grounding_embedder",
        lambda session: _lexical_embedder,
    )


def _seed() -> int:
    with Session(engine) as s:
        ingest_document(
            s, title="resume.md", source_kind=DocumentSource.paste,
            media_type=DocumentMediaType.md,
            data=b"I build python apis and run kubernetes clusters with leadership.",
            embedder=_lexical_embedder,
        )
        a = services.add_artifact(
            s, title="cover letter",
            body="I build python apis every day. I won a Nobel prize in chemistry.",
        )
        return a.id


def test_post_grounding_runs_check(client, fake_embedder):
    aid = _seed()
    r = client.post(f"/api/artifacts/{aid}/grounding")
    assert r.status_code == 200
    data = r.json()
    assert data["checked_count"] == 2
    assert data["unsupported_count"] == 1
    assert "[MISSING: I won a Nobel prize in chemistry.]" in data["annotated_body"]
    assert data["stale"] is False
    # the stored body is never mutated
    assert "[MISSING" not in client.get(f"/api/artifacts/{aid}").json()["body"]


def test_post_grounding_missing_artifact_404(client, fake_embedder):
    assert client.post("/api/artifacts/999999/grounding").status_code == 404


def test_post_grounding_empty_corpus_400(client, fake_embedder):
    with Session(engine) as s:
        aid = services.add_artifact(s, title="x", body="Some body text here.").id
    r = client.post(f"/api/artifacts/{aid}/grounding")
    assert r.status_code == 400
    assert "corpus is empty" in r.json()["detail"]


def test_post_grounding_missing_key_400(client, monkeypatch):
    def _no_key(session):
        raise RuntimeError("OpenAI API key is not configured (Settings or OH_OPENAI_API_KEY).")

    monkeypatch.setattr("app.routers.artifacts._grounding_embedder", _no_key)
    aid = _seed()
    r = client.post(f"/api/artifacts/{aid}/grounding")
    assert r.status_code == 400
    assert "OpenAI API key" in r.json()["detail"]


def test_get_grounding_before_check_404(client, fake_embedder):
    aid = _seed()
    assert client.get(f"/api/artifacts/{aid}/grounding").status_code == 404


def test_get_grounding_reports_stale_after_body_change(client, fake_embedder):
    aid = _seed()
    assert client.post(f"/api/artifacts/{aid}/grounding").status_code == 200
    with Session(engine) as s:
        a = s.get(Artifact, aid)
        a.body = "Completely different body now."
        s.add(a)
        s.commit()
    data = client.get(f"/api/artifacts/{aid}/grounding").json()
    assert data["stale"] is True
    # stale offsets must not be applied to the new body
    assert data["annotated_body"] == "Completely different body now."


def test_approve_flow_and_409(client, fake_embedder):
    aid = _seed()
    assert client.post(f"/api/artifacts/{aid}/approve").status_code == 409  # draft
    client.post(f"/api/artifacts/{aid}/grounding")
    r = client.post(f"/api/artifacts/{aid}/approve")
    assert r.status_code == 200
    assert r.json()["review_status"] == "approved"
    assert client.post(f"/api/artifacts/{aid}/approve").status_code == 409  # again
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_grounding_api.py -v`
Expected: FAIL — 404s/AttributeError (`_grounding_embedder` missing, routes absent)

- [ ] **Step 3: Extend `app/routers/artifacts.py`**

Replace the imports block at the top of the file with:

```python
"""Artifacts endpoints (generated deliverables; the canvas renders these)."""

from __future__ import annotations

import hashlib
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app import corpus_service, grounding_service, services
from app.db import get_session
from app.models import Artifact, ArtifactKind, GroundingReport
```

Append at the end of the file:

```python
# --------------------------------------------------------------------------- #
# Slice C: grounding check + review gate.
# --------------------------------------------------------------------------- #


def _grounding_embedder(session: Session):
    """Indirection point: tests monkeypatch this to inject a fake embedder."""
    return corpus_service.default_embedder(session)


class GroundingOut(BaseModel):
    artifact_id: int
    threshold: float
    embedding_model: str
    checked_count: int
    unsupported_count: int
    findings: list[dict]
    annotated_body: str
    stale: bool
    created_at: datetime


def _grounding_out(artifact: Artifact, report: GroundingReport) -> GroundingOut:
    stale = (
        hashlib.sha256(artifact.body.encode("utf-8")).hexdigest() != report.body_hash
    )
    # Stale offsets index a body that no longer exists — never apply them.
    annotated = (
        artifact.body if stale else grounding_service.annotate(artifact.body, report.findings)
    )
    return GroundingOut(
        artifact_id=artifact.id, threshold=report.threshold,
        embedding_model=report.embedding_model,
        checked_count=report.checked_count,
        unsupported_count=report.unsupported_count,
        findings=report.findings, annotated_body=annotated,
        stale=stale, created_at=report.created_at,
    )


@router.post("/{artifact_id}/grounding", response_model=GroundingOut)
def run_grounding(
    artifact_id: int, session: Session = Depends(get_session)
) -> GroundingOut:
    try:
        embedder = _grounding_embedder(session)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        report = grounding_service.run_grounding_check(
            session, artifact_id, embedder=embedder
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    artifact = session.get(Artifact, artifact_id)
    return _grounding_out(artifact, report)


@router.get("/{artifact_id}/grounding", response_model=GroundingOut)
def get_grounding(
    artifact_id: int, session: Session = Depends(get_session)
) -> GroundingOut:
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    report = session.exec(
        select(GroundingReport).where(GroundingReport.artifact_id == artifact_id)
    ).first()
    if report is None:
        raise HTTPException(
            status_code=404, detail="no grounding report — run a check first"
        )
    return _grounding_out(artifact, report)


@router.post("/{artifact_id}/approve", response_model=Artifact)
def approve(artifact_id: int, session: Session = Depends(get_session)) -> Artifact:
    try:
        return grounding_service.approve_artifact(session, artifact_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except grounding_service.InvalidStatusTransition as e:
        raise HTTPException(status_code=409, detail=str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_grounding_api.py -v; echo "EXIT=$?"`
Expected: 7 passed, EXIT=0

- [ ] **Step 5: Commit**

```bash
git add app/routers/artifacts.py tests/test_grounding_api.py
git commit -m "feat(grounding): /api/artifacts/{id}/grounding + /approve endpoints (run/report/stale/409 gate)"
```

---

### Task 8: Full-suite verification + spec status

**Files:**
- Modify: `docs/superpowers/specs/2026-06-11-grounding-review-gate-design.md:5` (Status line)

- [ ] **Step 1: Run the FULL suite**

Run: `.venv/bin/python -m pytest; echo "EXIT=$?"`
Expected: everything passes (slice B's 49 + ~30 new), 2 skipped (live probes), EXIT=0

- [ ] **Step 2: Quick smoke of the migration path on a copy of the real DB (if `data/app.db` exists)**

```bash
test -f data/app.db && .venv/bin/python - <<'EOF'
import shutil, tempfile, pathlib
from sqlmodel import create_engine
from app.db import _ensure_column

tmp = pathlib.Path(tempfile.mkdtemp()) / "app.db"
shutil.copy("data/app.db", tmp)
eng = create_engine(f"sqlite:///{tmp}")
_ensure_column(eng, "artifacts", "review_status", "VARCHAR DEFAULT 'draft'")
with eng.connect() as c:
    cols = [r[1] for r in c.exec_driver_sql("PRAGMA table_info(artifacts)")]
    assert "review_status" in cols, cols
    print("migration OK on real-DB copy:", cols)
EOF
```

Expected: `migration OK on real-DB copy: [...]` (or silently skipped if no `data/app.db`).
This runs on a COPY — the real DB is migrated by `init_db` at next app start.

- [ ] **Step 3: Update the spec status line**

Change line 5 of `docs/superpowers/specs/2026-06-11-grounding-review-gate-design.md`:

```markdown
**Status:** Implemented
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-06-11-grounding-review-gate-design.md
git commit -m "docs(spec): mark slice C grounding/review-gate spec implemented"
```

---

## Spec coverage map (self-review)

| Spec requirement | Task |
|---|---|
| `grounding_min_similarity` config (`OH_` env) | 1 |
| `ReviewStatus` + `Artifact.review_status` + `grounding_reports` table | 2 |
| Migration for pre-existing `artifacts` table | 2 |
| `split_sentences` (markdown-aware, offsets, abbrev guards, short-span skip) | 3 |
| `check_grounding` (batch embed, cosine, provenance, empty-corpus ValueError, config threshold) | 4 |
| `annotate` (derived, reverse-offset, never mutates) | 5 |
| `run_grounding_check` (persist/replace report, → needs_review) + `approve_artifact` (gate, conflict) | 6 |
| POST/GET grounding + POST approve endpoints; 400 key/corpus, 404, 409; stale flag | 7 |
| New version starts at draft | 6 (test) |
| Fully offline tests, no live gate | all |
