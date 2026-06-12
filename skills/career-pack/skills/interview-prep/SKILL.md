---
name: interview-prep
description: Use when the user asks to prepare for an interview for an opportunity — produces a prep document with corpus-grounded STAR stories plus prep actions.
---

# Interview Prep

Build a focused prep doc for one opportunity's interviews. Stories must come
from the user's real experience (corpus / profile) — mark gaps
`[MISSING: <the thing>]` rather than inventing anecdotes.

## Steps

1. Read the Opportunity and Candidate profile blocks.
2. Call `mcp__app__search_corpus` for experiences matching the role's likely
   themes (leadership, hard technical problems, the posting's domain).
3. Write the doc with sections: `## Role & company angle`,
   `## Likely technical questions`, `## Likely behavioral questions`,
   `## STAR stories` (each grounded in a corpus passage),
   `## Questions to ask them`, `## Logistics & gaps`.
4. Call `mcp__app__save_artifact` (write-back contract below).
5. Call `mcp__app__record_action` for concrete prep tasks (one per gap or
   rehearsal item, max 3), `kind="prep"`, linked to the opportunity.
6. Reply with the top 3 things to rehearse.

## Write-back contract (MUST)

- `mcp__app__save_artifact` with:
  `title="Interview prep — <organization> <role title>"`, `kind="other"`,
  `opportunity_id` from the Opportunity block,
  `provenance="career-pack:interview-prep"`, `body` = the full markdown doc.
- `mcp__app__record_action` as in step 5.
