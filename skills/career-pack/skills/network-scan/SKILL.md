---
name: network-scan
description: Use when the user wants to scan the companies where they know someone for job openings that match them — surfaces warm-intro opportunities.
---

# Network Scan

Find openings at companies where the user already has a contact, so they can
pursue roles with a warm introduction. Adapted from the proficiently network-scan
process for this project's Contacts + corpus.

## Steps

1. Read the Candidate profile, Job preferences (if present), and **Contacts**
   blocks. The Contacts block lists people grouped by their organization.
2. For each distinct organization that has a contact, use `WebSearch` (and
   `WebFetch` to confirm) to find LIVE current openings at that company that match
   the candidate's target titles and must-haves. Skip organizations with no
   relevant opening. Only keep roles you can source to a real posting URL.
3. For each genuinely matching opening (at most 10 total), call
   `mcp__app__save_opportunity`: `type="job"`, `title`, `organization`, `url`
   (the posting — REQUIRED), `summary` (why it fits AND that the user knows
   <contact name> there), `source="network-scan"`, `dedupe_key` = the URL.
4. For each saved opening, call `mcp__app__record_action`:
   `title="Ask <contact> about <role> at <organization>"`, `kind="outreach"`.
5. Never fabricate a posting, a URL, or a contact. Reply with a ranked,
   one-line-per-find summary naming the contact for each.

## Write-back contract (MUST)

- `mcp__app__save_opportunity` per find — `type="job"`, `url` REQUIRED,
  `source="network-scan"`, `dedupe_key` = the URL. Max 10 per scan.
- `mcp__app__record_action` per find — `kind="outreach"`, naming the contact for
  the warm intro.
