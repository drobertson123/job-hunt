---
name: draft-pursuit
description: Use when the user asks to draft outreach or a proposal for a business opportunity — corpus-grounded, never inventing capabilities or experience.
---

# Draft Pursuit (outreach / proposal)

Draft the document that opens or advances a business pursuit. It asserts the
candidate's capabilities to an external party — the grounding rules are
non-negotiable.

## Grounding rules (non-negotiable)

- Call `mcp__app__search_corpus` for every capability claim you plan to make
  (at least 2 queries) before writing.
- Every capability, past result, metric, and client reference MUST come from
  a corpus passage or the Candidate profile block; write
  `[MISSING: <the thing>]` instead of inventing.

## Steps

1. Read the Opportunity block, Candidate profile block, and optional Input
   block (angle, ask, constraints).
2. Decide the form from the user's ask: a short outreach MESSAGE
   (intro/pitch email) or a PROPOSAL document (scope, approach,
   deliverables, timeline; pricing only if the user gave numbers). Default
   to outreach for a first contact.
3. Run the corpus searches (grounding rules above).
4. Draft it — tight, specific to this opportunity, no generic filler.
5. Call `mcp__app__save_artifact` (contract below).
6. Reply with the draft's key angle and any `[MISSING: …]` gaps.

## Write-back contract (MUST)

- `mcp__app__save_artifact` with `opportunity_id` from the Opportunity
  block, `provenance="business-pack:draft-pursuit"`, `body` = the full
  markdown, and:
  - outreach message → `title="Outreach — <organization>"`,
    `kind="outreach"` (it will be auto-checked and land in review as
    `needs_review` — that is expected; do not try to approve it);
  - proposal document → `title="Proposal — <organization>"`,
    `kind="proposal"`.
