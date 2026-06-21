---
name: company-enrich
description: Use to research the company behind an opportunity and fill its structured profile (industry, size, ATS vendor, careers URL) — writes the Company row and links the opportunity.
---

# Company Enrich

Research the organization behind an opportunity and write its **structured**
company profile (not a prose brief). Use web search. Pass ONLY fields you
verified from a source — never invent a size, ATS vendor, careers URL, or
domain. Omit anything you cannot verify; omitted fields are left unchanged.

## Steps

1. Identify the organization and the opportunity `id` from the prompt's
   "Opportunity" block.
2. Use `WebSearch` (and `WebFetch` on promising pages) to find, where verifiable:
   `industry`, company `size`, `hq_location`, `ats_vendor`
   (e.g. Greenhouse, Lever, Workday, Ashby), `careers_url`, `domain`, and a
   one-line `summary`.
3. Call `mcp__app__record_company` (write-back contract below) with the verified
   fields and `link_opportunity_id` = the opportunity `id`.
4. Reply with 2–3 bullets: what you filled and what you could not verify.

## Constraints (MUST)

- `size` must be exactly one of: `startup`, `smb`, `mid`, `large`,
  `enterprise`, `unknown`. Map your research to the closest, or omit `size`.
- Never pass a guessed value. If a field is not supported by a source, omit it.

## Write-back contract (MUST)

- `mcp__app__record_company` with: `name` = the organization (verbatim from the
  Opportunity block's `organization`), `link_opportunity_id` = the opportunity
  `id`, plus each verified field (`industry`, `size`, `hq_location`,
  `ats_vendor`, `careers_url`, `domain`, `summary`).
