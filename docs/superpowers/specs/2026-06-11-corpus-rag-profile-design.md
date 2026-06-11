# Corpus / RAG + Profile Synthesis — Design

**Date:** 2026-06-11
**Phase:** 2, slice B (job track only)
**Status:** Approved (pending spec review)

## Context

Phase 2 ("authored career pack + fit") bundles ~5 independent pieces. On inspection the
corpus/RAG layer the master plan attributes to Phase 1 was **never built** — Phase 1 shipped
the schema, orchestration, and the normalizer probe, but no ingest/chunk/embed/search and no
profile synthesis. Grounding and anti-fabrication (later slices) depend on it, and the plan
calls it the cold-start onboarding that "gates the rest." So Phase 2 was decomposed into
sub-projects, and this slice (B) is brainstormed first.

Decomposition of Phase 2 (each gets its own spec → plan):

- **A — authored-skill seam:** wire filesystem-skill loading, author a minimal career
  `SKILL.md`, prove ONE capability end-to-end through the MCP write-back tools.
- **B — corpus/RAG + profile synthesis (THIS SPEC).**
- **C — grounding / anti-fabrication** (`[MISSING]`, review-before-send) — depends on B.
- **D — capabilities** (add-by-paste, company research, CV/ATS, interview prep, fit).
- **E — `.docx`/`.pdf` export + artifact versioning.**

## Purpose

Build the retrieval substrate plus structured profile synthesis: the user uploads/pastes their
career materials, the system stores embeddable chunks with provenance, supports similarity
retrieval, and synthesizes a structured `Profile` from the corpus. This is the onboarding that
unblocks grounding-dependent capabilities in later slices.

## Scope

- **In scope:** ingest (paste, `.txt`/`.md`, `.pdf`, `.docx`) → chunk → embed → store; cosine
  retrieval behind a service function + an `mcp__app__search_corpus` read tool; structured,
  re-runnable `Profile` synthesis; HTTP endpoints for upload/list/delete/synthesize/get-profile.
- **Out of scope:** consumers of retrieval (authored skills = slice A); `[MISSING]`-grounding /
  anti-fabrication enforcement logic (slice C); `.docx`/`.pdf` export (slice E); the `business`
  track (Phase 3); corpus-search UI endpoint (not chosen); a narrative profile artifact.

## Decisions (from brainstorming)

1. **Slice scope = substrate + profile synthesis** (not substrate-only).
2. **Inputs = paste + `.txt`/`.md` + `.pdf` + `.docx`** (binary parsing included).
3. **Profile output = a structured `Profile` row** (typed/JSON fields), re-runnable (overwrite);
   no narrative artifact in this slice.
4. **Retrieval exposed as** a Python `corpus_service.search()` **and** a thin
   `mcp__app__search_corpus` read tool. No HTTP search endpoint.
5. **Vector store = brute-force numpy cosine** (A1), embeddings stored as BLOBs in an ordinary
   table, hidden behind `corpus_service.search()` so a later swap to `sqlite-vec` is a one-file
   change. Chosen over `sqlite-vec` (extension-load risk, unproven in this Python) and a
   dedicated vector DB (heavyweight, breaks the single-`app.db` backup story). Correct at
   single-user scale (dozens of docs, a few thousand 1536-dim chunks → sub-10ms).
6. **Profile synthesis uses the local Claude CLI + JSON-validated pattern** the normalizer uses
   (async, injectable `query_fn`, Pydantic schema), **not** the Anthropic API. No `messages.parse`.
7. **Embedding client is injectable**; the default wraps OpenAI `text-embedding-3-small` with the
   settings-resolved key. Live calls are gated behind an opt-in env flag so the default test
   suite is fully offline.

## Data model (3 new tables in `app/models.py`)

```
Document
  id            int PK
  title         str               # filename or user-given label
  source_kind   enum(upload|paste)
  media_type    enum(pdf|docx|txt|md)   # a paste is stored as md
  raw_text      str               # extracted plain text
  content_hash  str  (indexed)    # sha256 of raw_text → dedup / idempotency
  char_count    int
  created_at    datetime

Chunk
  id              int PK
  document_id     int FK → Document  (cascade delete)
  seq             int                # order within the document
  text            str
  embedding       bytes              # numpy float32 .tobytes()
  embedding_model str
  created_at      datetime

Profile   (single re-runnable row)
  id              int PK
  headline        str | None
  summary         str | None
  skills          JSON list[str]
  experience      JSON list[obj]     # {title, org, dates, highlights[]}
  achievements    JSON list[str]
  target_titles   JSON list[str]
  locations       JSON list[str]
  synthesized_at  datetime
  source_doc_count int
```

## Components & data flow

### `app/corpus_service.py` (DB-aware substrate)
- `extract_text(*, filename, media_type, data) -> str` — dispatch by media type: `pypdf` (PDF),
  `python-docx` (DOCX), decode (txt/md), passthrough (paste). Rejects empty/garbled extraction.
- `chunk_text(text) -> list[str]` — deterministic; ~1000-char windows, ~150 overlap, split on
  paragraph/sentence boundaries. No embedding here (pure function, trivially testable).
- `embed(texts, *, embedder) -> list[list[float]]` — batches through the injectable embedder.
- `ingest_document(session, *, title, source_kind, media_type, data, embedder) -> Document` —
  extract → hash → (dedup: replace existing Document+Chunks with same hash) → chunk → embed →
  persist Document + Chunks in one transaction. Embedding failure rolls back (no partial doc).
- `search(session, query, *, embedder, k=8) -> list[ChunkHit]` — embed query, load chunk vectors,
  cosine in numpy, return top-k `ChunkHit(document_id, document_title, chunk_text, score)`.

### Default embedder (`app/embeddings.py` or within corpus_service)
- `OpenAIEmbedder` wrapping `openai` `text-embedding-3-small`; model from config; key from
  `settings_service.resolve_openai_key`. Lazy import of `openai` (mirrors the normalizer's lazy
  pattern) so the package's absence never breaks offline tests.

### `app/profile_service.py`
- `ProfileSchema` (Pydantic) mirrors the `Profile` JSON fields.
- `async synthesize_profile(session, *, query_fn=sdk_query) -> Profile` — reads the corpus broadly
  (concatenated document text, truncated to a safe budget), runs a single-turn tool-less
  `ClaudeAgentOptions(max_turns=1)` query, validates JSON into `ProfileSchema`, overwrites the
  single `Profile` row. Anti-fabrication is in the prompt: "use only what the corpus supports;
  omit unknown fields; never invent experience."

### `app/agent/tools.py`
- Add `search_corpus(query, k)` read tool wrapping `corpus_service.search`; returns formatted hits
  with provenance. Append to `ALL_TOOLS` (so it joins the allowlist). Read-only.

### `app/routers/corpus.py`
- `POST /corpus/documents` — multipart file upload OR JSON paste → `ingest_document`.
- `GET /corpus/documents` — list (no embeddings).
- `DELETE /corpus/documents/{id}` — delete document + chunks.
- `POST /corpus/profile/synthesize` — run synthesis, return the Profile.
- `GET /corpus/profile` — current Profile (or 404/empty if none).
- Register the router in `app/main.py`.

## Error handling

- **Missing OpenAI key** → clear 4xx / raised error at ingest & synthesis time; never a crash.
- **Empty / unparseable document** → rejected with a message; never persist zero-chunk documents.
- **Embedding API failure** → transaction rolls back; no partial document remains.
- **Re-upload of identical content** → idempotent via `content_hash` (replace, not duplicate).
- **Synthesis on an empty corpus** → return a clear "corpus is empty" error, not a fabricated profile.

## Testing

**Deterministic, offline (default suite):**
- Fake embedder producing stable hash-based vectors → `chunk_text` boundaries/overlap;
  `ingest_document` persistence + dedup-on-hash; `search` cosine ranking returns expected order
  and correct provenance.
- Committed tiny `.pdf` / `.docx` / `.md` / `.txt` fixtures → `extract_text` returns expected text.
- Fake `query_fn` returning canned JSON → `synthesize_profile` writes/overwrites the `Profile`
  row; assert the anti-fabrication prompt shape and that absent fields stay empty (not invented).

**Opt-in live gate (`OH_RUN_LIVE_PROBE`-style, skipped by default):**
- Real OpenAI embeddings + real local-CLI synthesis over a tiny committed fixture corpus:
  ingest → search returns a relevant chunk; synthesize → a `Profile` row with plausible,
  corpus-grounded fields. Keeps the default suite network-free.

## Risks / notes

- **sqlite-vec deferred, not rejected:** the `search()` interface preserves a cheap later swap if
  the corpus ever outgrows brute force.
- **OpenAI key + network** required for any live path; the Tailscale/PyPI DNS issue is resolved,
  but the live gate still needs a key, hence opt-in.
- **PDF/DOCX extraction quality** is inherently messy; the gate asserts non-empty, sane text on
  controlled fixtures, not perfect fidelity on arbitrary resumes.
- **Profile synthesis is non-deterministic**; the live gate shows feasibility, the deterministic
  tests cover the plumbing. Quality is a manual/eval concern, per the plan's testing note.
