---
name: content-library
description: Use to build or refresh the reusable content library — headline, summary, and achievement-bullet variants synthesized from the user's corpus.
---

# Content Library

Synthesize a small, reusable library of polished career blocks the tailoring
skills draw from. Everything must be grounded in the user's corpus — never invent
a metric, title, employer, or claim.

## Steps

1. Read the Candidate profile block. Call `mcp__app__search_corpus` several times
   for the user's strongest material (leadership, scale, domain wins, tooling).
2. From grounded material, compose:
   - **2-3 `headline` variants** — different positioning angles (e.g. a technical
     angle and a leadership angle). `audience` names the angle.
   - **2-3 `summary` variants** — 2-3 sentences each, audience-tailored
     (e.g. `technical`, `leadership`). `audience` names it.
   - **up to 10 `bullet`s** — the strongest achievement statements
     (action + scope + outcome), each traceable to a corpus passage.
3. For each block, call `mcp__app__save_content_block` (contract below). If a
   claim isn't supported by the corpus, do NOT save it.
4. Reply with how many blocks of each kind you saved.

## Write-back contract (MUST)

- `mcp__app__save_content_block` per block — `text` (the block), `kind`
  (`headline`/`summary`/`bullet`), `audience` (the angle, optional), `tags`
  (skills/domains it supports). Save only corpus-grounded content.
