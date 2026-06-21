# Content Library — Design (Phase C: intake-extracted concept)

## Where this came from
The `intake/` directory contained the user's hand-built **"Master reference
document for resume creation — synthesized from all resume versions on file"**:
a curated bank of multiple **headline options**, audience-tailored **summary
versions** (e.g. technical vs leadership), and reusable achievement bullets.
That is a process worth adopting: a curated, reusable, *variant* content bank that
tailoring draws from — distinct from the raw **corpus** (source documents) and the
single synthesized **Profile** (one identity). No content was copied; this is the
concept, re-implemented on the project's SQLite/MCP architecture.

## Goal
A **Content Library** of reusable career assets the agent synthesizes from the
corpus and that `cv-tailor` reuses — so tailoring assembles from polished, vetted
blocks instead of regenerating from scratch each time.

## Model — `ContentBlock` (new table)
- `id: int PK`
- `kind: ContentBlockKind` — `headline | summary | bullet | other`
- `audience: str = ""` — positioning tag, e.g. "technical", "leadership", "" = general
- `text: str` — the polished, reusable block
- `tags: list[str]` (JSON) — skills/domains it supports
- `provenance: str | None`
- `created_at: datetime`
New table → `create_all`; no migration.

## Service / tool / API
- `services.add_content_block / list_content_blocks(kind=None) / delete_content_block`.
- MCP write-back tool `mcp__app__save_content_block` (args `text` required, `kind`,
  `audience`, `tags`) → added to `ALL_TOOLS`.
- `app/routers/content.py`: `GET /api/content-blocks?kind=`, `DELETE /api/content-blocks/{id}`.

## Capability — `content-library`
`requires_opportunity=False`, `requires_input=False`, `include_profile=True`. The
skill searches the corpus for the candidate's strongest material and saves, via
`save_content_block`, a small set of: 2–3 **headline** variants (positioning),
2–3 audience-tailored **summary** variants, and the top ~10 achievement **bullets**
— each grounded in a corpus passage (anti-fabrication: never invent metrics/titles;
mark unsupported as `[MISSING:]` and skip saving it).

## Reuse in tailoring
`Capability` gains `include_content: bool = False`; `cv-tailor` sets it True. The
invoke router fetches `list_content_blocks` when the flag is set and inlines a
`content_library_block(blocks)` into the prompt. `cv-tailor`'s SKILL.md gains a
step: "prefer reusing/adapting matching library blocks (pick the headline/summary
variant that fits this role) over writing from scratch; all claims still grounded."

## UI
A **Library** canvas tab listing blocks grouped by kind (headline/summary/bullet)
with their audience tag, and a remove button. `api.ts` gains
`fetchContentBlocks`/`deleteContentBlock`.

## Testing
- service add/list(filter by kind)/delete round-trip.
- `save_content_block` tool persists a block.
- `content-library` capability registered (count 15→16); skill static checks pass.
- `cv-tailor` prompt includes a "Content library" section when blocks exist;
  `cover-letter` does not (include_content False there).
- API GET/DELETE; frontend `next build`.
Gate green. Constitution III honored — blocks are corpus-grounded; reuse keeps the
existing grounding/approval gate on the final artifact.
