# Corpus / RAG + Profile Synthesis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the corpus/RAG substrate (ingest → chunk → embed → cosine search) plus structured, re-runnable `Profile` synthesis, so the user can upload/paste career materials and the system retrieves grounded context and synthesizes a profile.

**Architecture:** Embeddings are stored as `float32` BLOBs in an ordinary `Chunk` table and searched by brute-force numpy cosine behind `corpus_service.search()` (swappable to `sqlite-vec` later). Embedding is done through an **injectable** embedder (default = OpenAI `text-embedding-3-small`); profile synthesis reuses the normalizer's local-CLI + JSON-validated pattern (async, injectable `query_fn`, Pydantic schema) — not the Anthropic API. The default test suite is fully offline via fakes; one opt-in env-gated test hits the real services.

**Tech Stack:** Python 3.12, SQLModel/SQLite, FastAPI, numpy, pypdf, python-docx, openai, claude-agent-sdk, pytest (+ pytest-asyncio `asyncio_mode=auto`).

**Spec:** `docs/superpowers/specs/2026-06-11-corpus-rag-profile-design.md`

**Conventions to follow (already in the codebase):**
- Models in `app/models.py`: naive-UTC `_utcnow()`, JSON via `Field(default_factory=..., sa_column=Column(JSON))`, int autoincrement PKs for child records (see `Action`/`Artifact`).
- Routers use prefix `/api/<name>` and `Depends(get_session)` (see `app/routers/notes.py`); register in `app/main.py`.
- MCP tools: `@tool("name", "desc", schema)` async returning `_ok(text)`, appended to `ALL_TOOLS` in `app/agent/tools.py` (see `save_opportunity`).
- Keys resolved via `settings_service.resolve_openai_key(session)`.
- Offline test command: `.venv/bin/python -m pytest` (NOT plain `uv run`, which re-resolves over the network).

---

### Task 1: Dependencies + config

**Files:**
- Modify: `pyproject.toml` (dependencies)
- Modify: `app/config.py:43-46` (add embedding model)
- Test: `tests/test_corpus_config.py`

- [ ] **Step 1: Add dependencies**

Run (DNS/PyPI works now):
```bash
cd /home/drobertson123/src/job-hunt
uv add numpy pypdf python-docx openai
```
Expected: resolves and writes `pyproject.toml` + `uv.lock`. If it times out, see the `tailscale-dns-blocks-pypi` note (point resolv.conf at a public DNS, retry).

- [ ] **Step 2: Write the failing test**

```python
# tests/test_corpus_config.py
from __future__ import annotations

from app.config import get_config


def test_embedding_model_default():
    assert get_config().embedding_model == "text-embedding-3-small"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_corpus_config.py -v`
Expected: FAIL — `AttributeError: 'AppConfig' object has no attribute 'embedding_model'`

- [ ] **Step 4: Add the config field**

In `app/config.py`, in the `# --- LLM models ...` block (right after `deep_analysis_model`), add:
```python
    # Embeddings (RAG corpus). OpenAI; key via settings_service.resolve_openai_key.
    embedding_model: str = "text-embedding-3-small"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_corpus_config.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock app/config.py tests/test_corpus_config.py
git commit -m "feat(corpus): add numpy/pypdf/docx/openai deps + embedding_model config"
```

---

### Task 2: Data model — Document, Chunk, Profile

**Files:**
- Modify: `app/models.py` (append new tables + enums; update module docstring list)
- Test: `tests/test_corpus_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_corpus_models.py
from __future__ import annotations

from sqlmodel import Session

from app.db import engine
from app.models import Chunk, Document, DocumentMediaType, DocumentSource, Profile


def test_document_chunk_roundtrip():
    with Session(engine) as s:
        doc = Document(
            title="resume.md",
            source_kind=DocumentSource.paste,
            media_type=DocumentMediaType.md,
            raw_text="hello world",
            content_hash="abc123",
            char_count=11,
        )
        s.add(doc)
        s.commit()
        s.refresh(doc)
        chunk = Chunk(
            document_id=doc.id, seq=0, text="hello world",
            embedding=b"\x00\x00", embedding_model="text-embedding-3-small",
        )
        s.add(chunk)
        s.commit()
        s.refresh(chunk)
        assert doc.id is not None and chunk.id is not None
        assert chunk.document_id == doc.id


def test_profile_json_fields_default_empty():
    p = Profile()
    assert p.skills == [] and p.experience == [] and p.target_titles == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_corpus_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'Document'`

- [ ] **Step 3: Append the models**

At the end of `app/models.py` add:
```python
class DocumentSource(str, Enum):
    upload = "upload"
    paste = "paste"


class DocumentMediaType(str, Enum):
    pdf = "pdf"
    docx = "docx"
    txt = "txt"
    md = "md"


class Document(SQLModel, table=True):
    __tablename__ = "corpus_documents"

    id: int | None = Field(default=None, primary_key=True)
    title: str
    source_kind: DocumentSource = DocumentSource.upload
    media_type: DocumentMediaType = DocumentMediaType.txt
    raw_text: str = ""
    content_hash: str = Field(index=True)  # sha256 of raw_text → dedup/idempotency
    char_count: int = 0
    created_at: datetime = Field(default_factory=_utcnow)


class Chunk(SQLModel, table=True):
    __tablename__ = "corpus_chunks"

    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="corpus_documents.id", index=True)
    seq: int = 0
    text: str = ""
    embedding: bytes = b""  # numpy float32 .tobytes()
    embedding_model: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class Profile(SQLModel, table=True):
    __tablename__ = "profile"

    id: int | None = Field(default=None, primary_key=True)
    headline: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    experience: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    achievements: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    target_titles: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    locations: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    source_doc_count: int = 0
    synthesized_at: datetime = Field(default_factory=_utcnow)
```

(Optional housekeeping: in the module docstring's "Later phases add" list, the names `corpus_documents, corpus_chunks` are now realized.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_corpus_models.py -v`
Expected: PASS (the session-scoped `init_db` fixture in `conftest.py` creates the new tables)

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_corpus_models.py
git commit -m "feat(corpus): Document, Chunk, Profile models"
```

---

### Task 3: Deterministic chunker

**Files:**
- Create: `app/corpus_service.py`
- Test: `tests/test_corpus_chunking.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_corpus_chunking.py
from __future__ import annotations

from app.corpus_service import chunk_text


def test_chunk_empty_returns_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_chunk_short_text_is_single_chunk():
    assert chunk_text("one short paragraph") == ["one short paragraph"]


def test_chunk_long_text_splits_with_overlap():
    text = " ".join(f"word{i}" for i in range(1000))  # ~6-7k chars
    chunks = chunk_text(text, size=1000, overlap=150)
    assert len(chunks) > 1
    assert all(len(c) <= 1000 for c in chunks)
    # overlap: end of chunk 0 reappears at the start of chunk 1
    tail = chunks[0][-50:]
    assert tail.split()[-1] in chunks[1]


def test_chunk_is_deterministic():
    text = "para one.\n\n" + ("alpha beta gamma " * 200)
    assert chunk_text(text) == chunk_text(text)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_corpus_chunking.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.corpus_service'`

- [ ] **Step 3: Create the module with the chunker**

```python
# app/corpus_service.py
"""Corpus/RAG substrate: ingest, chunk, embed, and cosine-search career docs.

Embeddings are stored as float32 BLOBs and searched by brute-force numpy cosine
behind `search()` (swappable to sqlite-vec later). The embedder is injectable so
the default test suite runs offline; the default wraps OpenAI text-embedding-3-small.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from sqlmodel import Session, delete, select

from app import settings_service
from app.config import get_config
from app.models import (
    Chunk,
    Document,
    DocumentMediaType,
    DocumentSource,
)

# An embedder maps a batch of texts to a batch of vectors.
Embedder = Callable[[list[str]], list[list[float]]]


def chunk_text(text: str, *, size: int = 1000, overlap: int = 150) -> list[str]:
    """Split text into overlapping windows, breaking on a nearby boundary.

    Deterministic and dependency-free so it is trivially testable.
    """
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    n = len(text)
    start = 0
    while start < n:
        end = min(start + size, n)
        if end < n:
            window = text[start:end]
            brk = max(
                window.rfind("\n\n"), window.rfind("\n"),
                window.rfind(". "), window.rfind(" "),
            )
            if brk > size // 2:
                end = start + brk + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_corpus_chunking.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/corpus_service.py tests/test_corpus_chunking.py
git commit -m "feat(corpus): deterministic chunk_text"
```

---

### Task 4: Text extraction (paste / txt / md / pdf / docx)

**Files:**
- Modify: `app/corpus_service.py` (add `extract_text`)
- Create fixtures: `tests/fixtures/corpus/sample.md`, `sample.txt`, `sample.pdf`, `sample.docx`
- Test: `tests/test_corpus_extract.py`

- [ ] **Step 1: Create text fixtures + generate binary fixtures**

Create `tests/fixtures/corpus/sample.md` with:
```markdown
# Jane Doe

Staff ML Engineer with PyTorch and MLOps experience.
```
Create `tests/fixtures/corpus/sample.txt` with:
```
Plain text resume for Jane Doe, ML engineer.
```
Generate the binary fixtures once (committed thereafter):
```bash
.venv/bin/python - <<'PY'
from pathlib import Path
d = Path("tests/fixtures/corpus"); d.mkdir(parents=True, exist_ok=True)
import pypdf
w = pypdf.PdfWriter(); w.add_blank_page(width=200, height=200)
# pypdf can't easily draw text; write a text-bearing PDF via reportlab-free trick:
PY
```
Because drawing text into a PDF needs a writer that embeds text, generate the PDF with `pypdf` is insufficient. Use this instead (no extra deps — `fpdf2` is NOT a dependency, so build the docx with python-docx and the pdf with a minimal hand-rolled writer is overkill). **Generate the PDF and DOCX like so:**
```bash
.venv/bin/python - <<'PY'
from pathlib import Path
d = Path("tests/fixtures/corpus"); d.mkdir(parents=True, exist_ok=True)

# DOCX via python-docx
from docx import Document as Docx
doc = Docx()
doc.add_paragraph("Jane Doe — Staff ML Engineer. PyTorch, MLOps, computer vision.")
doc.save(d / "sample.docx")

# PDF: write a tiny valid text PDF by hand (one line of text).
text = "Jane Doe Staff ML Engineer PyTorch MLOps"
stream = f"BT /F1 18 Tf 36 150 Td ({text}) Tj ET".encode()
objs = []
objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
objs.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>")
objs.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
out = bytearray(b"%PDF-1.4\n")
offsets = []
for i, body in enumerate(objs, start=1):
    offsets.append(len(out))
    out += b"%d 0 obj\n%s\nendobj\n" % (i, body)
xref = len(out)
out += b"xref\n0 %d\n" % (len(objs) + 1)
out += b"0000000000 65535 f \n"
for off in offsets:
    out += b"%010d 00000 n \n" % off
out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)
(d / "sample.pdf").write_bytes(bytes(out))
print("wrote fixtures")
PY
```
Verify pypdf can read it:
```bash
.venv/bin/python -c "import pypdf; print(repr(pypdf.PdfReader('tests/fixtures/corpus/sample.pdf').pages[0].extract_text()))"
```
Expected: a string containing `Jane Doe`. If empty, fall back to committing a real exported PDF from any editor with the same text — the test only asserts a substring.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_corpus_extract.py
from __future__ import annotations

from pathlib import Path

import pytest

from app.corpus_service import extract_text
from app.models import DocumentMediaType

FIX = Path(__file__).parent / "fixtures" / "corpus"


def test_extract_md_and_txt():
    md = extract_text(data=(FIX / "sample.md").read_bytes(), media_type=DocumentMediaType.md)
    assert "Jane Doe" in md and "MLOps" in md
    txt = extract_text(data=(FIX / "sample.txt").read_bytes(), media_type=DocumentMediaType.txt)
    assert "ML engineer" in txt


def test_extract_docx():
    out = extract_text(data=(FIX / "sample.docx").read_bytes(), media_type=DocumentMediaType.docx)
    assert "Jane Doe" in out and "PyTorch" in out


def test_extract_pdf():
    out = extract_text(data=(FIX / "sample.pdf").read_bytes(), media_type=DocumentMediaType.pdf)
    assert "Jane Doe" in out


def test_extract_empty_raises():
    with pytest.raises(ValueError):
        extract_text(data=b"   ", media_type=DocumentMediaType.txt)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_corpus_extract.py -v`
Expected: FAIL — `ImportError: cannot import name 'extract_text'`

- [ ] **Step 4: Implement `extract_text`**

Add to `app/corpus_service.py` (imports `io`; pypdf/docx imported lazily inside the branches so their absence never breaks unrelated tests):
```python
import io


def extract_text(*, data: bytes, media_type: DocumentMediaType) -> str:
    """Extract plain text from raw bytes by media type. Raises ValueError if empty."""
    if media_type in (DocumentMediaType.txt, DocumentMediaType.md):
        text = data.decode("utf-8", errors="replace")
    elif media_type == DocumentMediaType.pdf:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    elif media_type == DocumentMediaType.docx:
        import docx

        document = docx.Document(io.BytesIO(data))
        text = "\n".join(p.text for p in document.paragraphs)
    else:  # pragma: no cover - enum is exhaustive
        raise ValueError(f"unsupported media type: {media_type}")

    text = text.strip()
    if not text:
        raise ValueError("no extractable text in document")
    return text
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_corpus_extract.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/corpus_service.py tests/test_corpus_extract.py tests/fixtures/corpus
git commit -m "feat(corpus): extract_text for paste/txt/md/pdf/docx + fixtures"
```

---

### Task 5: Embedder contract + default OpenAI embedder

**Files:**
- Modify: `app/corpus_service.py` (add `default_embedder`)
- Test: `tests/test_corpus_embedder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_corpus_embedder.py
from __future__ import annotations

import pytest
from sqlmodel import Session

from app.corpus_service import default_embedder
from app.db import engine


def test_default_embedder_without_key_raises_clear_error():
    # No OpenAI key configured in the test settings table.
    with Session(engine) as s:
        with pytest.raises(RuntimeError, match="OpenAI API key"):
            default_embedder(s)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_corpus_embedder.py -v`
Expected: FAIL — `ImportError: cannot import name 'default_embedder'`

- [ ] **Step 3: Implement `default_embedder`**

Add to `app/corpus_service.py` (lazy `openai` import so package absence never breaks offline tests):
```python
def default_embedder(session: Session) -> Embedder:
    """Build an OpenAI-backed embedder using the settings-resolved key.

    Raises RuntimeError (not at import) if no key is configured.
    """
    api_key = settings_service.resolve_openai_key(session)
    if not api_key:
        raise RuntimeError("OpenAI API key is not configured (Settings or OH_OPENAI_API_KEY).")
    model = get_config().embedding_model

    def embed(texts: list[str]) -> list[list[float]]:
        import openai

        client = openai.OpenAI(api_key=api_key)
        resp = client.embeddings.create(model=model, input=texts)
        return [item.embedding for item in resp.data]

    return embed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_corpus_embedder.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/corpus_service.py tests/test_corpus_embedder.py
git commit -m "feat(corpus): default OpenAI embedder (lazy, key-resolved)"
```

---

### Task 6: ingest_document (extract → hash → dedup → chunk → embed → persist)

**Files:**
- Modify: `app/corpus_service.py` (add `_to_blob`, `ingest_document`)
- Test: `tests/test_corpus_ingest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_corpus_ingest.py
from __future__ import annotations

import hashlib

from sqlmodel import Session, select

from app.corpus_service import ingest_document
from app.db import engine
from app.models import Chunk, Document, DocumentMediaType, DocumentSource


def _fake_embedder(dim=8):
    def embed(texts):
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            out.append([b / 255.0 for b in h[:dim]])
        return out
    return embed


def test_ingest_persists_document_and_chunks():
    big = "Resume.\n\n" + ("alpha beta gamma delta " * 300)
    with Session(engine) as s:
        doc = ingest_document(
            s, title="resume.md", source_kind=DocumentSource.paste,
            media_type=DocumentMediaType.md, data=big.encode(),
            embedder=_fake_embedder(),
        )
        doc_id = doc.id
        chunks = s.exec(select(Chunk).where(Chunk.document_id == doc_id)).all()
    assert doc_id is not None
    assert len(chunks) > 1
    assert all(c.embedding and c.embedding_model for c in chunks)
    assert doc.char_count == len(big.strip())


def test_ingest_is_idempotent_on_content_hash():
    text = "identical content for dedup".encode()
    with Session(engine) as s:
        d1 = ingest_document(s, title="a.txt", source_kind=DocumentSource.upload,
                             media_type=DocumentMediaType.txt, data=text, embedder=_fake_embedder())
        d2 = ingest_document(s, title="a-again.txt", source_kind=DocumentSource.upload,
                             media_type=DocumentMediaType.txt, data=text, embedder=_fake_embedder())
        h = hashlib.sha256("identical content for dedup".encode()).hexdigest()
        docs = s.exec(select(Document).where(Document.content_hash == h)).all()
    assert len(docs) == 1  # replaced, not duplicated
    assert d2.id is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_corpus_ingest.py -v`
Expected: FAIL — `ImportError: cannot import name 'ingest_document'`

- [ ] **Step 3: Implement ingest**

Add to `app/corpus_service.py`:
```python
def _to_blob(vector: list[float]) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def ingest_document(
    session: Session,
    *,
    title: str,
    source_kind: DocumentSource,
    media_type: DocumentMediaType,
    data: bytes,
    embedder: Embedder,
) -> Document:
    """Extract → hash → (dedup-replace) → chunk → embed → persist atomically."""
    raw_text = extract_text(data=data, media_type=media_type)
    content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    # Idempotency: drop any existing document (and its chunks) with the same hash.
    existing = session.exec(
        select(Document).where(Document.content_hash == content_hash)
    ).all()
    for old in existing:
        session.exec(delete(Chunk).where(Chunk.document_id == old.id))
        session.delete(old)
    session.flush()

    pieces = chunk_text(raw_text)
    if not pieces:
        raise ValueError("document produced no chunks")
    vectors = embedder(pieces)
    if len(vectors) != len(pieces):
        raise ValueError("embedder returned wrong number of vectors")

    model = get_config().embedding_model
    doc = Document(
        title=title, source_kind=source_kind, media_type=media_type,
        raw_text=raw_text, content_hash=content_hash, char_count=len(raw_text),
    )
    session.add(doc)
    session.flush()  # assign doc.id
    for seq, (piece, vec) in enumerate(zip(pieces, vectors)):
        session.add(Chunk(
            document_id=doc.id, seq=seq, text=piece,
            embedding=_to_blob(vec), embedding_model=model,
        ))
    session.commit()
    session.refresh(doc)
    return doc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_corpus_ingest.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/corpus_service.py tests/test_corpus_ingest.py
git commit -m "feat(corpus): ingest_document with content-hash dedup"
```

---

### Task 7: Cosine search

**Files:**
- Modify: `app/corpus_service.py` (add `ChunkHit`, `search`)
- Test: `tests/test_corpus_search.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_corpus_search.py
from __future__ import annotations

from sqlmodel import Session

from app.corpus_service import ChunkHit, ingest_document, search
from app.db import engine
from app.models import DocumentMediaType, DocumentSource

VOCAB = ["python", "marketing", "kubernetes", "sales", "pytorch"]


def _lexical_embedder(texts):
    # term-frequency over a fixed vocab → meaningful cosine ranking
    return [[float(t.lower().count(w)) for w in VOCAB] for t in texts]


def test_search_ranks_relevant_chunk_first():
    with Session(engine) as s:
        ingest_document(s, title="eng.md", source_kind=DocumentSource.paste,
                        media_type=DocumentMediaType.md,
                        data=b"python python pytorch kubernetes backend engineer",
                        embedder=_lexical_embedder)
        ingest_document(s, title="mkt.md", source_kind=DocumentSource.paste,
                        media_type=DocumentMediaType.md,
                        data=b"marketing marketing sales brand campaigns",
                        embedder=_lexical_embedder)
        hits = search(s, "python kubernetes pytorch", embedder=_lexical_embedder, k=2)
    assert isinstance(hits[0], ChunkHit)
    assert "python" in hits[0].chunk_text
    assert hits[0].score >= hits[-1].score  # sorted descending
    assert hits[0].document_title == "eng.md"


def test_search_empty_corpus_returns_empty():
    # fresh hash so prior docs don't match; query an unrelated term
    with Session(engine) as s:
        hits = search(s, "nonexistent zzz", embedder=_lexical_embedder, k=5)
    assert isinstance(hits, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_corpus_search.py -v`
Expected: FAIL — `ImportError: cannot import name 'ChunkHit'`

- [ ] **Step 3: Implement search**

Add to `app/corpus_service.py`:
```python
@dataclass
class ChunkHit:
    chunk_id: int
    document_id: int
    document_title: str
    chunk_text: str
    score: float


def search(session: Session, query: str, *, embedder: Embedder, k: int = 8) -> list[ChunkHit]:
    """Embed the query and return the top-k chunks by cosine similarity, with provenance."""
    rows = session.exec(select(Chunk)).all()
    if not rows:
        return []
    q = np.asarray(embedder([query])[0], dtype=np.float32)
    mat = np.vstack([np.frombuffer(r.embedding, dtype=np.float32) for r in rows])
    qn = q / (np.linalg.norm(q) + 1e-12)
    mn = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12)
    scores = mn @ qn
    order = np.argsort(-scores)[:k]

    title_by_doc = {
        d.id: d.title
        for d in session.exec(
            select(Document).where(Document.id.in_([rows[i].document_id for i in order]))
        ).all()
    }
    hits: list[ChunkHit] = []
    for i in order:
        r = rows[int(i)]
        hits.append(ChunkHit(
            chunk_id=r.id, document_id=r.document_id,
            document_title=title_by_doc.get(r.document_id, "?"),
            chunk_text=r.text, score=float(scores[int(i)]),
        ))
    return hits
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_corpus_search.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/corpus_service.py tests/test_corpus_search.py
git commit -m "feat(corpus): brute-force cosine search with provenance"
```

---

### Task 8: `search_corpus` MCP read tool

**Files:**
- Modify: `app/agent/tools.py` (add tool, append to `ALL_TOOLS`)
- Test: `tests/test_corpus_tool.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_corpus_tool.py
from __future__ import annotations

from sqlmodel import Session

from app.agent.tools import ALL_TOOL_NAMES, search_corpus
from app.corpus_service import ingest_document
from app.db import engine
from app.models import DocumentMediaType, DocumentSource


def _lexical_embedder(texts):
    vocab = ["python", "marketing"]
    return [[float(t.lower().count(w)) for w in vocab] for t in texts]


def test_search_corpus_tool_is_registered():
    assert "mcp__app__search_corpus" in ALL_TOOL_NAMES


async def test_search_corpus_returns_provenance_text(monkeypatch):
    with Session(engine) as s:
        ingest_document(s, title="py.md", source_kind=DocumentSource.paste,
                        media_type=DocumentMediaType.md,
                        data=b"python python backend", embedder=_lexical_embedder)
    # Force the tool to use the deterministic embedder instead of OpenAI.
    monkeypatch.setattr("app.agent.tools._corpus_embedder",
                        lambda session: _lexical_embedder)
    result = await search_corpus({"query": "python", "k": 3})
    text = result["content"][0]["text"]
    assert "py.md" in text and "python" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_corpus_tool.py -v`
Expected: FAIL — `ImportError: cannot import name 'search_corpus'`

- [ ] **Step 3: Implement the tool**

In `app/agent/tools.py`, add an import near the top with the other `app` imports:
```python
from app import corpus_service
from app import settings_service
```
Add a seam so tests can inject a deterministic embedder, plus the tool (place above `ALL_TOOLS`):
```python
def _corpus_embedder(session: Session):
    """Indirection point: tests monkeypatch this to inject a fake embedder."""
    return corpus_service.default_embedder(session)


@tool(
    "search_corpus",
    "Search the user's career corpus (their uploaded CV, notes, and documents) "
    "for passages relevant to a query. Returns ranked excerpts with their source.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "k": {"type": "integer", "description": "max results (default 8)"},
        },
        "required": ["query"],
    },
)
async def search_corpus(args: dict[str, Any]) -> dict[str, Any]:
    query = (args.get("query") or "").strip()
    if not query:
        return _ok("No query provided.")
    k = int(args.get("k") or 8)
    with Session(engine) as s:
        embedder = _corpus_embedder(s)
        hits = corpus_service.search(s, query, embedder=embedder, k=k)
    if not hits:
        return _ok("No matching passages in the corpus.")
    lines = [f"[{h.document_title}] (score {h.score:.3f})\n{h.chunk_text}" for h in hits]
    return _ok("\n\n---\n\n".join(lines))
```
Append `search_corpus` to the `ALL_TOOLS` list:
```python
ALL_TOOLS = [
    save_note,
    save_opportunity,
    update_pipeline_status,
    record_action,
    save_artifact,
    record_decision,
    search_corpus,
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_corpus_tool.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/agent/tools.py tests/test_corpus_tool.py
git commit -m "feat(corpus): mcp__app__search_corpus read tool"
```

---

### Task 9: Profile synthesis (local-CLI + JSON, injectable query_fn)

**Files:**
- Create: `app/profile_service.py`
- Test: `tests/test_profile_synthesis.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_profile_synthesis.py
from __future__ import annotations

from collections.abc import AsyncIterator

from claude_agent_sdk import AssistantMessage, TextBlock
from sqlmodel import Session, select

from app.corpus_service import ingest_document
from app.db import engine
from app.models import Document, DocumentMediaType, DocumentSource, Profile
from app.profile_service import ProfileSchema, synthesize_profile


def _fake_embedder(texts):
    return [[1.0, 0.0] for _ in texts]


def _fake_query(reply_text: str, calls: list[dict]):
    async def fake(*, prompt, options) -> AsyncIterator:
        calls.append({"prompt": prompt, "options": options})
        yield AssistantMessage(content=[TextBlock(text=reply_text)], model="fake-model")
    return fake


async def test_synthesize_writes_profile_row_and_grounds_prompt():
    with Session(engine) as s:
        ingest_document(s, title="cv.md", source_kind=DocumentSource.paste,
                        media_type=DocumentMediaType.md,
                        data=b"Jane Doe. Staff ML Engineer. PyTorch, MLOps.",
                        embedder=_fake_embedder)
    reply = (
        '{"headline": "Staff ML Engineer", "summary": "ML platform leader.", '
        '"skills": ["PyTorch", "MLOps"], "experience": [], "achievements": [], '
        '"target_titles": ["Staff ML Engineer"], "locations": []}'
    )
    calls: list[dict] = []
    with Session(engine) as s:
        profile = await synthesize_profile(s, query_fn=_fake_query(reply, calls))
        profile_id = profile.id

    with Session(engine) as s:
        row = s.get(Profile, profile_id)
    assert row is not None
    assert row.headline == "Staff ML Engineer"
    assert "PyTorch" in row.skills
    assert row.source_doc_count == 1
    # corpus text is in the prompt (grounding) + anti-fabrication instruction present
    assert "Jane Doe" in calls[0]["prompt"]
    assert "never invent" in calls[0]["prompt"].lower()


async def test_synthesize_overwrites_single_row():
    reply = '{"headline": "Second", "summary": null, "skills": [], "experience": [], "achievements": [], "target_titles": [], "locations": []}'
    calls: list[dict] = []
    with Session(engine) as s:
        await synthesize_profile(s, query_fn=_fake_query(reply, calls))
        await synthesize_profile(s, query_fn=_fake_query(reply, calls))
    with Session(engine) as s:
        rows = s.exec(select(Profile)).all()
    assert len(rows) == 1 and rows[0].headline == "Second"


async def test_synthesize_empty_corpus_raises():
    import pytest
    # use a fresh in-memory expectation: clear documents first
    with Session(engine) as s:
        for d in s.exec(select(Document)).all():
            s.delete(d)
        s.commit()
    calls: list[dict] = []
    with pytest.raises(ValueError, match="empty"):
        with Session(engine) as s:
            await synthesize_profile(s, query_fn=_fake_query("{}", calls))
```

> Note: `test_synthesize_overwrites_single_row` and `test_synthesize_empty_corpus_raises` both mutate the shared corpus. Run the file as a unit; within it, `overwrites` runs after `writes_profile_row` (which ingests a doc) and `empty_corpus` clears docs last. Keep them in this order.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_profile_synthesis.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.profile_service'`

- [ ] **Step 3: Implement profile synthesis**

```python
# app/profile_service.py
"""Profile synthesis: read the corpus broadly and write a structured Profile row.

Reuses the normalizer's mechanism: a single-turn, tool-less local Claude CLI
session (Agent SDK, CLI auth — no API key), with JSON validated by Pydantic.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock
from claude_agent_sdk import query as sdk_query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.config import get_config
from app.models import Document, Profile

_CORPUS_CHAR_BUDGET = 24000


class ProfileSchema(BaseModel):
    headline: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[dict] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    target_titles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)


_INSTRUCTION = (
    "You build a structured career profile of a single person from their own "
    "documents. Use ONLY what the documents support. If a field is not evidenced, "
    "leave it empty — never invent experience, employers, titles, or skills."
)


def _build_prompt(corpus_text: str) -> str:
    schema = json.dumps(ProfileSchema.model_json_schema())
    return (
        f"{_INSTRUCTION}\n\n"
        "Respond with ONE JSON object and nothing else — no prose, no code fences. "
        f"It must conform to this JSON Schema:\n{schema}\n\n"
        "Here are the person's documents between the markers:\n"
        f"<corpus>\n{corpus_text}\n</corpus>"
    )


def _extract_json(text: str) -> str:
    s = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        return s[start : end + 1]
    return s


async def synthesize_profile(
    session: Session,
    *,
    query_fn: Callable[..., AsyncIterator[Any]] = sdk_query,
) -> Profile:
    """Synthesize and persist (overwrite) the single Profile row from the corpus."""
    docs = session.exec(select(Document).order_by(Document.created_at)).all()
    if not docs:
        raise ValueError("corpus is empty; nothing to synthesize")
    corpus_text = "\n\n".join(f"# {d.title}\n{d.raw_text}" for d in docs)[:_CORPUS_CHAR_BUDGET]

    model = get_config().default_agent_model
    options = ClaudeAgentOptions(model=model, max_turns=1)
    chunks: list[str] = []
    async for message in query_fn(prompt=_build_prompt(corpus_text), options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock) and block.text:
                    chunks.append(block.text)
    parsed = ProfileSchema.model_validate_json(_extract_json("".join(chunks)))

    row = session.exec(select(Profile)).first()
    if row is None:
        row = Profile()
    row.headline = parsed.headline
    row.summary = parsed.summary
    row.skills = parsed.skills
    row.experience = parsed.experience
    row.achievements = parsed.achievements
    row.target_titles = parsed.target_titles
    row.locations = parsed.locations
    row.source_doc_count = len(docs)
    from app.models import _utcnow

    row.synthesized_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_profile_synthesis.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/profile_service.py tests/test_profile_synthesis.py
git commit -m "feat(corpus): structured Profile synthesis via local CLI + JSON"
```

---

### Task 10: HTTP router

**Files:**
- Create: `app/routers/corpus.py`
- Modify: `app/main.py` (import + include router)
- Test: `tests/test_corpus_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_corpus_api.py
from __future__ import annotations

import app.routers.corpus as corpus_router
from app.models import DocumentMediaType


def _lexical_embedder(texts):
    return [[float(t.lower().count("python")), 1.0] for t in texts]


def test_paste_list_and_delete(client, monkeypatch):
    monkeypatch.setattr(corpus_router, "_embedder_for",
                        lambda session: _lexical_embedder)
    # paste a document
    r = client.post("/api/corpus/documents",
                    json={"title": "note.md", "text": "python python engineer"})
    assert r.status_code == 200, r.text
    doc_id = r.json()["id"]

    # it shows up in the list (without embeddings)
    listed = client.get("/api/corpus/documents").json()
    assert any(d["id"] == doc_id for d in listed)

    # delete it
    assert client.delete(f"/api/corpus/documents/{doc_id}").status_code == 200
    listed2 = client.get("/api/corpus/documents").json()
    assert all(d["id"] != doc_id for d in listed2)


def test_synthesize_and_get_profile(client, monkeypatch):
    monkeypatch.setattr(corpus_router, "_embedder_for",
                        lambda session: _lexical_embedder)

    async def fake_synth(session, *, query_fn=None):
        from app.models import Profile
        from sqlmodel import select
        row = session.exec(select(Profile)).first() or Profile()
        row.headline = "Synthesized"
        row.skills = ["python"]
        session.add(row); session.commit(); session.refresh(row)
        return row

    monkeypatch.setattr(corpus_router, "synthesize_profile", fake_synth)

    client.post("/api/corpus/documents", json={"title": "cv.md", "text": "python dev"})
    r = client.post("/api/corpus/profile/synthesize")
    assert r.status_code == 200, r.text
    assert r.json()["headline"] == "Synthesized"

    g = client.get("/api/corpus/profile")
    assert g.status_code == 200 and g.json()["skills"] == ["python"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_corpus_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.corpus'`

- [ ] **Step 3: Create the router**

```python
# app/routers/corpus.py
"""Corpus endpoints: upload/paste career docs, list/delete, synthesize profile."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from app import corpus_service
from app.db import get_session
from app.models import Document, DocumentMediaType, DocumentSource, Profile
from app.profile_service import synthesize_profile

router = APIRouter(prefix="/api/corpus", tags=["corpus"])

_EXT_TO_MEDIA = {
    "pdf": DocumentMediaType.pdf, "docx": DocumentMediaType.docx,
    "txt": DocumentMediaType.txt, "md": DocumentMediaType.md,
    "markdown": DocumentMediaType.md,
}


def _embedder_for(session: Session):
    """Indirection point: tests monkeypatch this to inject a fake embedder."""
    return corpus_service.default_embedder(session)


class PasteIn(BaseModel):
    title: str
    text: str


class DocumentOut(BaseModel):
    id: int
    title: str
    source_kind: DocumentSource
    media_type: DocumentMediaType
    char_count: int


# NOTE: paste (JSON) and upload (multipart) MUST be separate routes — FastAPI
# cannot accept a JSON body and File/Form on the same endpoint (Content-Type clash).


@router.post("/documents", response_model=DocumentOut)
def add_pasted_document(
    body: PasteIn,
    session: Session = Depends(get_session),
) -> Document:
    try:
        embedder = _embedder_for(session)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        return corpus_service.ingest_document(
            session, title=body.title, source_kind=DocumentSource.paste,
            media_type=DocumentMediaType.md, data=body.text.encode("utf-8"),
            embedder=embedder,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/documents/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    session: Session = Depends(get_session),
) -> Document:
    try:
        embedder = _embedder_for(session)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    media = _EXT_TO_MEDIA.get(ext)
    if media is None:
        raise HTTPException(status_code=400, detail=f"unsupported file type: .{ext}")
    data = await file.read()
    try:
        return corpus_service.ingest_document(
            session, title=title or file.filename or "upload",
            source_kind=DocumentSource.upload, media_type=media,
            data=data, embedder=embedder,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(session: Session = Depends(get_session)) -> list[Document]:
    return session.exec(select(Document).order_by(Document.created_at.desc())).all()


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, session: Session = Depends(get_session)) -> dict:
    from app.models import Chunk
    from sqlmodel import delete as sql_delete

    doc = session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="not found")
    session.exec(sql_delete(Chunk).where(Chunk.document_id == doc_id))
    session.delete(doc)
    session.commit()
    return {"deleted": doc_id}


@router.post("/profile/synthesize", response_model=Profile)
async def synthesize(session: Session = Depends(get_session)) -> Profile:
    try:
        return await synthesize_profile(session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/profile", response_model=Profile | None)
def get_profile(session: Session = Depends(get_session)) -> Profile | None:
    return session.exec(select(Profile)).first()
```

- [ ] **Step 4: Register the router**

In `app/main.py`, add `corpus` to the routers import block and include it after `attention`:
```python
from app.routers import (
    actions,
    artifacts,
    attention,
    chat,
    corpus,
    health,
    notes,
    opportunities,
    runs,
    settings,
)
```
and:
```python
app.include_router(attention.router)
app.include_router(corpus.router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_corpus_api.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add app/routers/corpus.py app/main.py tests/test_corpus_api.py
git commit -m "feat(corpus): /api/corpus endpoints (upload/paste, list, delete, profile)"
```

---

### Task 11: Opt-in live gate (real OpenAI embeddings + real CLI synthesis)

**Files:**
- Create fixture: `tests/fixtures/corpus/live_brief.md`
- Test: `tests/test_corpus_live.py`

- [ ] **Step 1: Create the fixture**

`tests/fixtures/corpus/live_brief.md`:
```markdown
# Candidate Brief — Jane Doe

Jane Doe is a Staff Machine Learning Engineer based in Boston, open to remote US roles.
She has 9 years of experience building model-serving platforms with PyTorch and Kubernetes,
led MLOps for a 30-person org, and is targeting Staff/Principal ML Engineer positions.
```

- [ ] **Step 2: Write the live test (skipped by default)**

```python
# tests/test_corpus_live.py
from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlmodel import Session

from app.corpus_service import default_embedder, ingest_document, search
from app.db import engine
from app.models import DocumentMediaType, DocumentSource, Profile
from app.profile_service import synthesize_profile

FIX = Path(__file__).parent / "fixtures" / "corpus" / "live_brief.md"


@pytest.mark.skipif(
    not os.environ.get("OH_RUN_LIVE_PROBE"),
    reason="set OH_RUN_LIVE_PROBE=1 to run the live corpus probe (needs OpenAI key + authed claude CLI)",
)
async def test_live_ingest_search_and_synthesize():
    with Session(engine) as s:
        embedder = default_embedder(s)  # raises clearly if no key
        ingest_document(s, title="live_brief.md", source_kind=DocumentSource.upload,
                        media_type=DocumentMediaType.md, data=FIX.read_bytes(),
                        embedder=embedder)
        hits = search(s, "PyTorch model serving experience", embedder=embedder, k=3)
        assert hits and "PyTorch" in hits[0].chunk_text

        profile = await synthesize_profile(s)
        pid = profile.id
    with Session(engine) as s:
        row = s.get(Profile, pid)
    assert row is not None
    assert row.skills, "profile should extract at least one corpus-grounded skill"
    assert any("engineer" in t.lower() for t in row.target_titles)
```

- [ ] **Step 3: Verify it skips without the flag**

Run: `.venv/bin/python -m pytest tests/test_corpus_live.py -v`
Expected: 1 skipped

- [ ] **Step 4: (Manual, when a key is configured) run the live gate**

Set the OpenAI key in the DB Settings (or `OH_OPENAI_API_KEY`), ensure the `claude` CLI is authed, then:
```bash
OH_RUN_LIVE_PROBE=1 .venv/bin/python -m pytest tests/test_corpus_live.py -v
```
Expected: PASS — real embeddings rank the PyTorch chunk first; real CLI synthesis writes a corpus-grounded Profile.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/corpus/live_brief.md tests/test_corpus_live.py
git commit -m "test(corpus): opt-in live gate (real embeddings + CLI synthesis)"
```

---

### Task 12: Full-suite verification

- [ ] **Step 1: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all green except the live probes skipped (the normalizer live probe + the corpus live probe). No failures.

- [ ] **Step 2: Update project memory**

Append to `~/.claude/projects/-home-drobertson123-src-job-hunt/memory/project-opportunity-hunter.md`: Phase 2 slice B (corpus/RAG + profile synthesis) built — models, `corpus_service`, `profile_service`, `search_corpus` tool, `/api/corpus` router; brute-force numpy cosine; injectable embedder; profile synthesis via local CLI; live gate opt-in.

- [ ] **Step 3: Commit (if memory file tracked) / done**

The branch `feature/phase2-corpus-rag` is ready for `superpowers:finishing-a-development-branch`.

---

## Self-Review

**Spec coverage:**
- Ingest paste/txt/md/pdf/docx → Tasks 4, 6, 10. ✓
- Chunk → Task 3. ✓
- Embed (injectable, OpenAI default) → Tasks 5, 6. ✓
- Store embeddings as BLOB → Task 2 (`Chunk.embedding`), Task 6 (`_to_blob`). ✓
- Cosine search + provenance → Task 7. ✓
- `search()` + `mcp__app__search_corpus` tool → Tasks 7, 8. ✓
- Structured re-runnable `Profile` synthesis (CLI+JSON, not API) → Tasks 2, 9. ✓
- HTTP endpoints (upload/list/delete/synthesize/get) → Task 10. ✓
- Idempotency on content_hash → Task 6. ✓
- Error handling (missing key, empty doc, empty corpus) → Tasks 5, 4, 9, 10. ✓
- Offline default suite via fakes + opt-in live gate → all unit tasks + Task 11. ✓
- Deps + config → Task 1. ✓

**Type consistency:** `Embedder = Callable[[list[str]], list[list[float]]]` used uniformly; `ingest_document`, `search`, `default_embedder`, `_corpus_embedder`/`_embedder_for` (the test injection seams) consistent; `ChunkHit` fields match across Task 7 and Task 8; `ProfileSchema` fields match `Profile` columns (Task 2 ↔ Task 9). `DocumentMediaType`/`DocumentSource` names consistent throughout.

**Placeholder scan:** No TBD/TODO; every code step shows complete code; the PDF fixture generation is fully scripted with a fallback note. The one judgment call (fixture generation) includes a verification command.

**Note on test isolation:** `conftest.py` uses one session-scoped DB. Tests that assert corpus emptiness (`test_search_empty_corpus_returns_empty`, `synthesize` tests) account for shared state by querying their own inserted rows or clearing first; ordering notes are included where mutation order matters.
