---
name: discover-opportunities
description: Use when the user asks to find or discover business opportunities — RFPs, grants, consulting or fractional leads, startup angles — via web search matched to their profile. Saves structured opportunity rows.
---

# Discover Opportunities

Sweep the web for concrete business opportunities matching the candidate
profile. Quality over quantity: a row with no source URL is worse than no
row — never fabricate an opportunity.

## Steps

1. Read the Candidate profile block (skills, target titles, locations) and
   the optional Input block (a focus, e.g. "grants for ML tooling").
2. Use `WebSearch` (and `WebFetch` to confirm promising hits) to find LIVE
   opportunities: RFPs, grants, consulting/fractional leads, partnership or
   startup angles. Prefer sources with deadlines and concrete asks.
3. Keep at most the 10 best matches. Skip anything you cannot source to a
   URL.
4. For each kept find, call `mcp__app__save_opportunity` (contract below).
5. Call `mcp__app__record_action` once (contract below).
6. Reply with a ranked one-line-per-find summary.

## Write-back contract (MUST)

- `mcp__app__save_opportunity` per distinct find with: `type="business"`,
  `title`, `organization`, `url` (the source — REQUIRED), `summary` (2-3
  sentences including why it matches the profile), `source="discovery"`,
  `dedupe_key` = the URL, `details` containing `opportunity_kind` (one of
  `rfp|grant|startup|fractional|partnership`) plus `value_estimate` /
  `deadline` ONLY when the source states them.
- Maximum 10 `save_opportunity` calls per sweep.
- `mcp__app__record_action` once with:
  `title="Triage discovered opportunities"`, `kind="research"`.

Do NOT save an artifact; this capability produces structured rows only.
