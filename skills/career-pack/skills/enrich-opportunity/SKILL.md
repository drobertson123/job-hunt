---
name: enrich-opportunity
description: Use when the user pastes a job posting or asks to add a job/opportunity to their pipeline — extracts it into a structured opportunity row plus a follow-up action.
---

# Enrich Opportunity (add-by-paste)

Turn a pasted job posting (or a rough description of one) into a structured
opportunity in the pipeline. Extract only what the text actually says — never
guess salary, location, or seniority that is not stated.

## Steps

1. Read the pasted posting in the prompt's "Input" section.
2. Extract: title, organization, url (if present), location, a 2-3 sentence
   summary, and type-specific details (salary, seniority, employment_type,
   skills — only when stated).
3. Compute `dedupe_key`: the posting URL if present, else
   `<organization>|<title>` lowercased.
4. Call `mcp__app__save_opportunity` (write-back contract below).
5. Call `mcp__app__record_action` for the obvious next step.
6. Reply with a 1-2 sentence confirmation naming the opportunity.

## Write-back contract (MUST)

- `mcp__app__save_opportunity` with: `type="job"` (or `"business"` when it is
  clearly not employment), `title`, `organization`, `url`, `location`,
  `summary`, `source="paste"`, `dedupe_key` (step 3), `details` (only stated
  fields).
- `mcp__app__record_action` with:
  `title="Review & qualify: <organization> — <title>"`, `kind="research"`, and
  the saved opportunity's id as `opportunity_id` (use the id echoed back by
  save_opportunity).

Do NOT save an artifact; this capability produces structured rows only.
