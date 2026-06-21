---
name: cv-tailor
description: Use when the user asks to tailor their CV/resume for an opportunity — produces an ATS-friendly CV artifact grounded in their corpus, never inventing experience.
---

# CV Tailor (ATS, corpus-grounded)

Produce a CV tailored to one opportunity, grounded EXCLUSIVELY in the user's
corpus. This document asserts facts about the user — fabrication is the one
unforgivable failure.

## Grounding rules (non-negotiable)

- Before writing, call `mcp__app__search_corpus` for each major requirement in
  the opportunity (role skills, domain, leadership, tooling) — at least 3
  queries.
- Every experience claim, employer, date, metric, and skill MUST come from a
  corpus passage or the Candidate profile block. If the posting wants
  something you cannot find, write `[MISSING: <the thing>]` in its place
  instead of inventing it.
- Do not inflate titles, dates, or numbers. Reword freely; never add facts.

## ATS rules

- Standard section headings: Summary, Skills, Experience, Education.
- Plain markdown: no tables, no images, no multi-column tricks.
- Mirror the posting's exact keyword spellings where the corpus supports them.

## Steps

1. Read the Opportunity and Candidate profile blocks. If a **Content library**
   block is present in the prompt, prefer selecting or adapting the headline and
   summary variant that best fits this role and reusing matching achievement
   bullets rather than writing from scratch — all reused claims are already
   corpus-grounded.
2. Run the corpus searches (grounding rules above).
3. Draft the CV: summary targeted at the role, skills list limited to
   supported skills, reverse-chronological experience with supported bullets.
4. Call `mcp__app__save_artifact` (write-back contract below).
5. Reply with what you emphasized and list any `[MISSING: …]` gaps.

## Write-back contract (MUST)

- `mcp__app__save_artifact` with: `title="CV — <organization> <role title>"`,
  `kind="cv"`, `opportunity_id` from the Opportunity block,
  `provenance="career-pack:cv-tailor"`, `body` = the full markdown CV.

The backend automatically runs a grounding check on this artifact; it lands in
review as `needs_review`. That is expected — do not try to approve it.
