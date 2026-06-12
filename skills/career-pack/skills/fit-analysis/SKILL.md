---
name: fit-analysis
description: Use when the user asks how well an opportunity fits them, or to score/compare an opportunity — produces a scored fit-analysis artifact and a decision row. Re-runnable.
---

# Fit Analysis

Score how well one opportunity fits the candidate. Be honest and
decision-useful: the user triages their pipeline with these scores, so an
inflated score is worse than a low one. Re-running on the same opportunity is
expected — each run saves a new artifact version and a new decision row.

## Steps

1. Read the Opportunity and Candidate profile blocks. If the profile block is
   empty, call `mcp__app__search_corpus` for the role's main requirements.
2. Score each dimension 1-5 with one sentence of evidence: skills match,
   seniority match, domain match, location/logistics, growth potential.
3. Compute overall = mean of the dimensions, one decimal.
4. Write the analysis in markdown: a score table, `## Strengths`,
   `## Gaps & risks`, `## Verdict` (pursue / deprioritize / pass — and why).
5. Call `mcp__app__save_artifact` then `mcp__app__record_decision`
   (write-back contract below).
6. Reply with the overall score and the verdict sentence.

## Write-back contract (MUST)

- `mcp__app__save_artifact` with:
  `title="Fit analysis — <organization> <role title>"`, `kind="fit_analysis"`,
  `opportunity_id` from the Opportunity block,
  `provenance="career-pack:fit-analysis"`, `body` = the full markdown
  analysis.
- `mcp__app__record_decision` with:
  `summary="Fit <overall>/5 — <verdict word>: <role title> @ <organization>"`,
  `kind="choice"`, `opportunity_id`, `rationale` = the 2-3 decisive reasons.
