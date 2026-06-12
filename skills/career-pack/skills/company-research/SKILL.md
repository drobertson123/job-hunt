---
name: company-research
description: Use when the user asks to research a company or an opportunity's organization — produces a sourced research-brief artifact linked to the opportunity.
---

# Company Research

Build a concise, sourced research brief on the organization behind an
opportunity. Use web search; cite sources. Facts you could not verify must be
written as `[MISSING: <what you looked for>]` — never invented.

## Steps

1. Identify the organization and role from the prompt's "Opportunity" block.
2. Use `WebSearch` (and `WebFetch` on promising pages) to gather: overview &
   products, size/funding/recent news, tech-stack signals, culture signals,
   and anything bearing on this specific role.
3. Write the brief in markdown with these sections: `## Company overview`,
   `## Products & market`, `## Funding & news`, `## Tech & engineering signals`,
   `## Culture signals`, `## Relevance to this role`, `## Sources` (URLs).
4. Call `mcp__app__save_artifact` (write-back contract below).
5. If you learned concrete fields the opportunity row lacks (canonical url, HQ
   location), also call `mcp__app__save_opportunity` passing the SAME
   `dedupe_key` shown in the Opportunity block, to update it idempotently.
6. Reply with a 3-bullet summary of the most decision-relevant findings.

## Write-back contract (MUST)

- `mcp__app__save_artifact` with: `title="Research brief — <organization>"`,
  `kind="research_brief"`, `opportunity_id` from the Opportunity block,
  `provenance="career-pack:company-research"`, `body` = the full markdown
  brief.
