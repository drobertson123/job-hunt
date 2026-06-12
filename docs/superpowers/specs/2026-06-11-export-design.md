# Export — docx/pdf + export-time review gate (Phase 2 slice E)

**Date:** 2026-06-11
**Status:** Implemented (plan docs/superpowers/plans/2026-06-11-export.md)
**Decided with user:** persist + download (not ephemeral); `approved` gate on
generative kinds only; pandoc + weasyprint renderer.

## Goal

Approved materials leave the app as real documents: any artifact's markdown
body exports to `.docx` and `.pdf`, persisted under `data/exports/` and
downloadable from the UI. Export is where the slice-C review gate gets teeth:
generative artifacts (the ones that assert facts about the user and leave the
house) cannot export unless `approved`.

## Scope

- **In:** `app/export_service.py` (gate + orchestration, injectable renderer);
  pandoc renderer with weasyprint PDF engine + small print CSS;
  `POST /api/artifacts/{id}/export` + `GET /api/artifacts/{id}/export/{format}`;
  per-artifact docx/pdf buttons in the canvas; toolchain install
  (`uv add weasyprint`, apt pango libs) with smoke test; offline orchestration
  tests + real-render smoke tests.
- **Out:** editing exports; templates/themes beyond one CSS file; export of
  anything but the artifact body (no cover pages); emailing/sending; export
  history UI; business-track concerns (Phase 3).

## 1. Export service (`app/export_service.py`)

`export_artifact(session, artifact_id, format, *, renderer=render_with_pandoc) -> ExportResult`

- `LookupError` if the artifact doesn't exist (router → 404).
- Only `ArtifactFormat.docx` / `ArtifactFormat.pdf` are valid export formats;
  the router rejects anything else with 422 (`markdown` is the body's own
  format, not an export target).
- **Gate:** if `artifact.kind ∈ grounding_service.GENERATIVE_KINDS` (the
  slice-A/D constant — reused, single source of truth) and
  `artifact.review_status != approved`, raise `ExportNotAllowed` (router →
  409, message tells the user to run the grounding check and approve first).
  Non-generative kinds (research_brief, fit_analysis, note, other, …) export
  from any status — they're internal working documents.
- Render `artifact.body` (markdown) to bytes via the injectable `renderer`
  callable; write to `cfg.exports_dir / f"artifact-{artifact.id}-v{artifact.version}.{ext}"`.
  `exports_dir` is a new `AppConfig` field defaulting to `data_dir / "exports"`,
  created by `ensure_dirs`.
- Update the row: `file_path` = the just-written path (informational, "latest
  export"); `format` stays `markdown` — the body remains canonical, and one
  row can have both a docx and a pdf export on disk (paths are deterministic
  from id+version+ext, so the DB doesn't need to track each one).
- Staleness is structurally impossible per row: bodies are never mutated (new
  versions are new rows — slice C invariant), so an export always matches its
  row's body.
- `ExportResult` dataclass: `artifact_id`, `format`, `path`, `download_url`.

## 2. Renderer (pandoc + weasyprint)

`render_with_pandoc(body_md: str, format: ArtifactFormat) -> bytes` — one
subprocess call:

- docx: `pandoc -f markdown -t docx -o <tmp>` (pandoc 3.1.3 already on the
  box; handles headings, bullets, bold, and the fit-analysis score tables).
- pdf: `pandoc -f markdown -o <tmp>.pdf --pdf-engine=weasyprint --css app/export.css`.
  `app/export.css` is a small print stylesheet (page margins, system font
  stack, table borders, heading sizes) — the only theming in this slice.
- Missing pandoc or a failing weasyprint engine raises `RendererUnavailable`
  with an actionable message (router → 503). Render failures on valid input
  (pandoc non-zero exit) raise `RenderFailed` (router → 500 with stderr tail).

**Toolchain install is plan Task 1** (fail fast on the riskiest step):
`uv add weasyprint` — **no apt packages were needed on this WSL2 box**: weasyprint
69.0 imported cleanly with system pango/harfbuzz already present. The apt command
(`sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi-dev`)
is retained as a fallback for machines that lack these system libs. Smoke-test
`pandoc -f markdown -o /tmp/t.pdf --pdf-engine=weasyprint` and `-t docx`.
The Tailscale-DNS/PyPI blocker is resolved (verified 2026-06-11: public DNS
works), so installs are unblocked.

## 3. Endpoints (on the artifacts router)

- `POST /api/artifacts/{id}/export?format=docx|pdf` → runs `export_artifact`,
  returns `ExportResult` JSON. Errors: 404 missing artifact, 409 gate
  (`ExportNotAllowed`), 422 invalid format, 503 toolchain missing, 500 render
  failure.
- `GET /api/artifacts/{id}/export/{format}` → `FileResponse` of the persisted
  file with `Content-Disposition` filename
  `"<sanitized title> v<version>.<ext>"` (sanitizer strips path separators and
  control chars; falls back to `artifact-<id>`). 404 if that format was never
  exported (no render-on-GET — POST is the only render path).
- Media types: docx `application/vnd.openxmlformats-officedocument.wordprocessingml.document`,
  pdf `application/pdf`.

## 4. Frontend (minimal)

On each artifact card in the canvas: two small buttons, `docx` and `pdf`.
Click → `POST /api/artifacts/{id}/export?format=…`; on success navigate to
`download_url` (browser download — works from the phone over Tailscale); on
409/503 show the error detail in the existing error style. No review-queue UI,
no export history — out of scope.

## 5. Testing

Offline-by-default orchestration tests with a **fake renderer** (returns
`b"PK-fake"` / `b"%PDF-fake"`):

- Gate matrix: draft `cv` → 409; `needs_review` `cv` → 409; approved `cv` →
  200; draft `research_brief` → 200 (gate is generative-kinds-only).
- File lands at the deterministic path; row's `file_path` updated; `format`
  still `markdown`.
- Download roundtrip: POST then GET returns the bytes with the right
  Content-Disposition; GET before any POST → 404; unknown artifact → 404;
  `format=markdown` → 422.
- Filename sanitization (title with `/`, newline, em-dash).
- Renderer-unavailable path → 503 (fake raising `RendererUnavailable`).

**Real-render smoke tests** (run by default, `skipif` pandoc/weasyprint
absent): export a markdown body with a heading, bullets, and a table; assert
docx bytes start with `PK` and pdf bytes with `%PDF`, and both files are
non-trivially sized. No live agent, no network — everything is local.

## Risks / notes

- weasyprint's system libs (pango/cairo stack) on WSL2 are the one moving
  part; Task 1 smoke-tests before any code is written.
- pandoc markdown flavor differences (e.g. line-break handling) are accepted —
  artifacts are generated by our own skills in plain markdown.
- `file_path` holds only the *latest* export; both formats remain reachable
  because paths are deterministic. If export history ever matters, that's a
  new table, not this slice.
- Export filenames include the artifact title — sanitization is asserted in
  tests because titles come from agent output.
