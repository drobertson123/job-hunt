---
name: qualify-opportunity
description: Use when the user asks to qualify, triage, or decide whether to pursue a business opportunity — moves its pipeline stage with evidence and records the decision.
---

# Qualify Opportunity

Decide whether one business opportunity deserves pursuit. Be honest: the
pipeline only works if `lost` is used freely. Evidence over enthusiasm.

## Steps

1. Read the Opportunity block (including `details`: opportunity_kind,
   value_estimate, deadline) and the Candidate profile block.
2. Assess: capability fit (can the candidate credibly deliver?), effort vs
   value, timing/deadline feasibility, competition/odds.
3. Pick the new stage: `analyzing` (promising, needs a deep dive), `active`
   (clear yes, start pursuing), or `lost` (pass — say why). Never leave it
   at `qualifying`.
4. Call `mcp__app__update_pipeline_status` then `mcp__app__record_decision`
   (contract below).
5. Reply with the verdict and the 2-3 decisive reasons.

## Write-back contract (MUST)

- `mcp__app__update_pipeline_status` with: `opportunity_id` from the
  Opportunity block, `stage` from step 3, `rationale` (required — the
  decisive evidence).
- `mcp__app__record_decision` with:
  `summary="Qualified <title>: <verdict>"`, `kind="choice"`,
  `opportunity_id`, `rationale` = the 2-3 decisive reasons.

Do NOT save an artifact; this capability produces structured rows only.
