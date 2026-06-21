# Network-Scan + Apply-Prep Capabilities — Design

> **Attribution:** Adapts the `network-scan` and `apply` skills + ATS reference
> from [proficientlyjobs/proficiently-claude-skills](https://github.com/proficientlyjobs/proficiently-claude-skills)
> (MIT). Concepts re-implemented on this project's SQLite/MCP architecture — no
> browser automation, no copied text. The original reads `~/.proficiently/*` files
> and drives Claude-in-Chrome; this project uses the corpus, the Contacts table,
> and write-back tools.

## Goal
Two new career-pack capabilities that extend the process engine:
- **network-scan** — scan the companies where the user has a contact for openings
  that match them (warm-intro opportunities). Synergizes with the Google Contacts
  import just shipped.
- **apply-prep** — assemble an *application kit* (docs checklist + ATS field
  guidance + reusable answers) for one opportunity, WITHOUT auto-filling forms
  (no browser tooling in this agent).

## network-scan
`requires_opportunity=False`, `include_profile=True`, `include_contacts=True`
(new flag). The capability invoke path inlines the user's Contacts (grouped by
organization) via a new `contacts_block`. The skill WebSearches each org for live
openings matching the candidate, saves `type="job"` opportunities (source
`network-scan`, dedup on URL) and an `outreach` action naming the contact.

## apply-prep
`requires_opportunity=True`, `requires_input=False`, `include_profile=True`.
Detects the ATS from the posting/URL (Greenhouse/Lever/Workday/other) using a new
project reference `docs/references/ats-patterns.md`, and produces a kit artifact:
checklist (tailored resume + cover letter, flag if missing), ATS-specific fields
+ gotchas, and reusable answers (name/email/phone/LinkedIn/location/work-auth/
sponsorship/EEO defaulted to decline) filled from profile/corpus with `[MISSING:]`
for gaps. Anti-fabrication: never invent personal data.

## Wiring
- `Capability` gains `include_contacts: bool = False` (default keeps others
  unchanged); `contacts_block(contacts)` in capabilities; `build_prompt` gains a
  `contacts` param and appends the block when the flag is set.
- `capabilities` router invoke fetches `services.list_contacts(session)` when
  `cap.include_contacts` and passes it to `build_prompt`.
- Two `Capability` entries + two `skills/career-pack/skills/{network-scan,
  apply-prep}/SKILL.md`. Static count tests 13→15; `EXPECTED_SKILLS` + the
  `by_name` set updated. `ATTRIBUTION.md` updated to present-tense these two.

## Testing
- `build_prompt` for `network-scan` includes "Contacts (grouped by organization):"
  with a seeded contact's org; `apply-prep` includes the opportunity and NOT the
  contacts block.
- Both skills pass the career-pack static checks (frontmatter name, `## Write-back
  contract`, `mcp__app__`).
- The invoke router fetches contacts for network-scan (covered via the prompt test
  / a router test if cheap).
Gate green. Constitution III honored (apply-prep grounded; network-scan saves only
real sourced postings).
