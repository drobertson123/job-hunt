---
name: analyze-opportunity
description: Use when the user asks for a deep analysis of a business opportunity — market, competition, effort vs value, risks — saved as a research-brief artifact plus next-step actions.
---

# Analyze Opportunity

Produce a decision-grade analysis brief for one business opportunity. Use
`WebSearch`/`WebFetch` where public facts help; write `[MISSING: <what you
looked for>]` for anything you could not verify rather than guessing.

## Steps

1. Read the Opportunity block (including `details`).
2. Research what is verifiable: the organization, the market, comparable
   deals/awards, typical terms for this `opportunity_kind`.
3. Write the brief in markdown with sections: `## Opportunity shape`,
   `## Market & competition`, `## Effort vs value`, `## Risks`,
   `## Verdict & next steps`, `## Sources` (URLs).
4. Call `mcp__app__save_artifact` (contract below).
5. Call `mcp__app__record_action` for the concrete next steps (max 3).
6. Reply with the verdict paragraph.

## Write-back contract (MUST)

- `mcp__app__save_artifact` with: `title="Analysis — <title>"`,
  `kind="research_brief"`, `opportunity_id` from the Opportunity block,
  `provenance="business-pack:analyze-opportunity"`, `body` = the full
  markdown brief.
- `mcp__app__record_action` per next step (max 3), `kind="research"` or
  `kind="followup"`, linked to the opportunity.
