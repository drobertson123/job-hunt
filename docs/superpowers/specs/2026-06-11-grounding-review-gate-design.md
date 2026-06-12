# Grounding / Anti-Fabrication + Review Gate — Design

**Date:** 2026-06-11
**Phase:** 2, slice C (job track only)
**Status:** Approved (pending spec review)

## Context

The master plan's core anti-fabrication promise: generated materials must be *grounded in the
corpus* — "mark `[MISSING]`, don't fabricate" — with a review-before-send step. Slice B shipped
the corpus substrate (ingest/chunk/embed/search) and profile synthesis; prompts already say
"never invent," but nothing *checks* output, and `Artifact` has no review state. This slice
builds the checking substrate and the gate. Slice D capabilities will run their output through
it; slice E export will enforce it.

Position in the Phase 2 decomposition: A = authored-skill seam; B = corpus/RAG + profile
(done); **C = grounding / anti-fabrication (THIS SPEC)**; D = capabilities; E = export +
enforcement.

## Purpose

Given an artifact's text and the corpus, flag which sentences are corpus-supported (with
provenance) and which are not, produce a `[MISSING]`-annotated copy for human review, and add a
machine-checkable review lifecycle (`draft → needs_review → approved`) to `Artifact`.

## Scope

- **In scope:** `grounding_service` (sentence splitting, embedding-similarity scoring against
  corpus chunks, structured report, annotated text); `GroundingReport` persistence;
  `Artifact.review_status` + transitions; HTTP endpoints to run a check, fetch the report, and
  approve; config-tunable similarity threshold.
- **Out of scope:** `.docx`/`.pdf` export and export-time enforcement of `approved` (slice E);
  wiring slice D capabilities through the checker (slice D); any review-queue UI; LLM-judge
  verification (explicitly not chosen); the `business` track.

## Decisions (from brainstorming)

1. **Shape = substrate + verifier + review gate**: a reusable `grounding_service` proven
   offline on fixtures, plus the Artifact review lifecycle. Not a one-off check inside a
   single capability.
2. **Verify mechanism = embedding-similarity threshold** (user override of the hybrid
   retrieval+LLM-judge recommendation): embed each sentence, cosine-match against corpus
   chunks, below threshold = unsupported. Fully offline, deterministic, cheap; **no LLM in the
   verify path**, so this slice needs **no live gate**.
3. **Granularity = sentence-level**, deterministic rule-based splitter. No factual-claim
   filter, no LLM claim extraction. Degenerate-input guard only (very short spans skipped).
4. **Output = structured report + annotated text**: per-sentence findings drive the review UI;
   an annotated copy with `[MISSING]` markers is what a human reads. The stored artifact body
   is **never mutated**.
5. **Review gate = status enum + approve endpoint**: check → `needs_review`; human approval →
   `approved`. Artifacts are append-only versioned, so a new version is a new row defaulting
   to `draft` — approval never needs explicit invalidation on edit.

## Known limitation (designed-in, stated up front)

Cosine similarity measures **topical closeness, not entailment**. It reliably flags claims
whose subject is absent from the corpus (the dominant fabrication mode) but cannot catch a
fabricated specific that stays on-topic ("led a **300**-person org" scores high against "led a
**30**-person org"). The grounding score is therefore a **review aid that surfaces low-support
spans**; the human approval step is the actual authority. The report exposes raw scores and
provenance so the reviewer can judge, and so the threshold can be calibrated from real runs.

## Data model

```
ReviewStatus  enum: draft | needs_review | approved

Artifact (existing table; one new column)
  review_status   ReviewStatus = draft

GroundingReport   (new table; one current row per artifact, replaced on re-check)
  id               int PK
  artifact_id      int FK → Artifact  (unique)
  body_hash        str                # sha256 of the body that was checked → staleness detection
  threshold        float              # threshold used for this run
  embedding_model  str
  findings         JSON list[obj]     # per sentence: {text, start, end, score,
                                      #   chunk_id|None, document_title|None, supported}
  checked_count    int                # sentences scored
  unsupported_count int
  created_at       datetime
```

Annotated text is **derived** (body + findings offsets), not stored.

## Components & data flow

### `app/grounding_service.py` (mirrors `corpus_service` conventions)

- `split_sentences(text) -> list[Span]` — deterministic, markdown-aware: headings, list-item
  markers, and blank lines are structural separators; sentence boundaries on `.` `!` `?` with
  abbreviation guards. `Span = (text, start, end)` with exact char offsets into the original
  body. Spans under ~3 words are skipped (signatures, "Sincerely," headings) — a degenerate-
  input guard, not a factual filter.
- `check_grounding(session, text, *, embedder, threshold=None) -> GroundingResult` — split,
  embed all sentences in **one batch** via the injectable `Embedder` (same type as slice B;
  default `default_embedder`), score each against all corpus chunks with the same numpy-cosine
  routine as `corpus_service.search`, take the best match per sentence. `threshold=None` reads
  `grounding_min_similarity` from config. **Raises `ValueError` on empty corpus** — checking
  against nothing would mark everything `[MISSING]`, misleading rather than safe.
- `annotate(text, findings) -> str` — pure function; returns a copy with
  `[MISSING: <sentence>]` wrapping unsupported sentences, built from offsets (apply in reverse
  offset order so earlier offsets stay valid).
- `run_grounding_check(session, artifact_id, *, embedder) -> GroundingReport` — load artifact,
  `check_grounding` on its body, persist the report (replace any existing row for that
  artifact), set `review_status = needs_review`. 404-style error on missing artifact.
- `approve_artifact(session, artifact_id) -> Artifact` — valid **only** from `needs_review`
  (conflict error otherwise: an unchecked `draft` cannot be approved — that *is* the gate).

### Config (`app/config.py`)

- `grounding_min_similarity: float = 0.40` (`OH_GROUNDING_MIN_SIMILARITY`) — deliberately
  conservative default for `text-embedding-3-small`; tunable without code changes.

### `app/routers/artifacts.py` (extend existing router)

- `POST /api/artifacts/{id}/grounding` — run the check, return report summary + findings.
  Uses the same `_embedder_for(session)` seam pattern as the corpus router (missing OpenAI
  key → clean 4xx). `ValueError` (empty corpus) → 400.
- `GET /api/artifacts/{id}/grounding` — current report + derived annotated text + a `stale`
  bool (`body_hash` mismatch vs current body). 404 if never checked.
- `POST /api/artifacts/{id}/approve` — `needs_review → approved`; 409 from any other status.

## Error handling

- **Empty corpus** → `ValueError` → 400 with a "ingest corpus documents first" message.
- **Missing OpenAI key** → the existing `default_embedder` `RuntimeError` → clean 4xx (same
  contract as corpus endpoints).
- **Approve from `draft` or `approved`** → 409 with the current status in the message.
- **Stale report** (body changed after check — possible via direct DB edits or future paths)
  → surfaced as `stale: true` on GET, never silently treated as current.
- **Artifact not found** → 404 on all three endpoints.

## Testing (entirely offline — no live gate)

Deterministic fake embedders from slice B (lexical / hash-based) + fixture corpus and artifact
texts:

- **Splitter:** markdown structures (headings, bullets, paragraphs), abbreviation guards,
  offset exactness, short-span skipping.
- **Scoring:** with a lexical embedder, corpus-supported sentences score above threshold and
  carry correct chunk/document provenance; off-corpus sentences fall below and are flagged.
- **Annotation:** `[MISSING]` markers land on exactly the unsupported sentences; supported
  text byte-identical; original body unchanged; multiple unsupported spans handled (reverse-
  offset application).
- **Empty corpus** → `ValueError`; router → 400.
- **Lifecycle:** check sets `needs_review` and persists the report; re-check replaces (not
  duplicates) the report row; approve from `needs_review` works; approve from `draft` /
  `approved` → 409; a new artifact version (new row) starts at `draft`.
- **Staleness:** mutate the body hash → GET reports `stale: true`.
- **Threshold config:** `OH_GROUNDING_MIN_SIMILARITY` override changes supported/unsupported
  classification.

## Risks / notes

- **Topical-similarity blind spot** (see Known limitation) — accepted; the human gate is the
  authority. If real use shows too many on-topic fabrications slipping through, an LLM-judge
  second pass can be added later *behind the same service seam* without schema changes.
- **Boilerplate noise:** sentence-level (no factual filter) means generic phrases ("I am
  excited to apply") may flag as `[MISSING]`. Accepted trade-off from brainstorming; the
  threshold is tunable and the report shows scores, so calibration is data-driven.
- **Threshold default (0.40) is a guess** until real-embedding runs exist; the report stores
  the threshold used per run, so re-checks after tuning are comparable.
- **Single-embedding-model assumption** carries over from slice B's `search()`; the grounding
  report records `embedding_model` per run for forward compatibility.
