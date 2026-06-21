---
name: cover-letter
description: Use when the user asks for a cover letter for an opportunity — produces a corpus-grounded cover-letter artifact, never inventing experience.
---

# Cover Letter (corpus-grounded)

Write a cover letter for ONE opportunity, grounded EXCLUSIVELY in the user's
corpus and profile. This document asserts facts about the user — fabrication is
the one unforgivable failure.

## Grounding rules (non-negotiable)

- Before writing, call `mcp__app__search_corpus` for the role's key requirements
  (skills, domain, leadership, tooling) — at least 3 queries.
- Every claim, employer, metric, and skill MUST come from a corpus passage or the
  Candidate profile block. If the posting wants something you cannot find, write
  `[MISSING: <the thing>]` instead of inventing it.
- Never inflate titles, dates, or numbers. Reword freely; never add facts.

## Steps

1. Read the Opportunity and Candidate profile blocks.
2. Run the corpus searches (grounding rules above).
3. Draft the letter in markdown: a greeting; an opening hook tying the
   candidate's strongest corpus-supported background to this role; 2–3
   paragraphs each substantiating a value claim with a supported example; a
   concise close. Keep it under ~400 words and specific to this opportunity.
4. Call `mcp__app__save_artifact` (write-back contract below).
5. Reply with the angle you took and list any `[MISSING: …]` gaps.

## Write-back contract (MUST)

- `mcp__app__save_artifact` with: `title="Cover letter — <organization> <role>"`,
  `kind="cover_letter"`, `opportunity_id` from the Opportunity block,
  `provenance="career-pack:cover-letter"`, `body` = the full markdown letter.

The backend automatically grounds this artifact; it lands as `needs_review`.
That is expected — do not try to approve it.
