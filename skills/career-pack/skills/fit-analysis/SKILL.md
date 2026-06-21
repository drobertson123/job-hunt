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

1. Read the Opportunity, Candidate profile, and **Job preferences** blocks. If the
   profile block is empty, call `mcp__app__search_corpus` for the role's main
   requirements.
2. **Apply the preferences rubric first (decisive):**
   - **Dealbreakers** — if the opportunity matches ANY dealbreaker, the rating is
     **Skip**. Name the dealbreaker(s) and do not bother scoring dimensions.
   - **Must-haves** — count how many are met. Few met → likely **Low**.
   - **Nice-to-haves** — for opportunities that clear the must-haves.
   - **Rating:** **High** = no dealbreakers + all must-haves + ≥2 nice-to-haves;
     **Medium** = no dealbreakers + most must-haves (or all must-haves, few
     nice-to-haves); **Low** = no dealbreakers but significant must-have gaps;
     **Skip** = any dealbreaker. If no preferences are set, infer reasonable ones
     from the profile/corpus and say so.
3. Score each dimension 1-5 with one sentence of corpus/profile-grounded evidence:
   skills match, seniority match, domain match, location/logistics, growth.
4. Compute overall = mean of the dimensions, one decimal.
5. Write the analysis in markdown: the **Rating** (High/Medium/Low/Skip) and why,
   the score table, `## Strengths`, `## Gaps & risks`, `## Verdict`
   (pursue / deprioritize / pass — must agree with the rating).
6. Call `mcp__app__save_artifact` then `mcp__app__record_decision` (contract below).
7. Reply with the rating, the overall score, and the verdict sentence.

## Write-back contract (MUST)

- `mcp__app__save_artifact` with:
  `title="Fit analysis — <organization> <role title>"`, `kind="fit_analysis"`,
  `opportunity_id` from the Opportunity block,
  `provenance="career-pack:fit-analysis"`, `body` = the full markdown
  analysis.
- `mcp__app__record_decision` with:
  `summary="<Rating> · Fit <overall>/5 — <verdict word>: <role title> @ <organization>"`,
  `kind="choice"`, `opportunity_id`, `rationale` = the 2-3 decisive reasons.
