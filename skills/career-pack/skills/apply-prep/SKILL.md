---
name: apply-prep
description: Use when the user is ready to apply to an opportunity — assembles an application kit (what to submit, ATS field guidance, reusable answers). Does not auto-fill forms.
---

# Apply Prep

Assemble everything needed to submit an application for ONE opportunity. This does
NOT fill web forms (no browser automation) — it prepares a kit the user submits.
Adapted from the proficiently apply process; ATS knowledge lives in
`docs/references/ats-patterns.md`.

## Steps

1. Read the Opportunity and Candidate profile blocks, and the Input (an
   application/ATS URL, if the user gave one).
2. Identify the ATS from the URL/posting when possible — Greenhouse, Lever,
   Workday, or other — and recall its field layout + gotchas from
   `docs/references/ats-patterns.md`.
3. Assemble the kit in markdown:
   - **Checklist** — tailored resume + cover letter (if either is missing, say so
     and suggest running `cv-tailor` / `cover-letter` first) plus any
     opportunity-specific items.
   - **ATS** — which system, its key fields, and known gotchas. If you can't tell,
     say so.
   - **Reusable answers** — name, email, phone, LinkedIn, location, work
     authorization, visa sponsorship, EEO (default "Decline to self-identify"),
     filled from the profile/corpus. Mark anything you cannot ground as
     `[MISSING: <field>]`.
4. Call `mcp__app__save_artifact` (contract below).
5. Reply with the ATS, what's ready, and what's still needed.

## Anti-fabrication (non-negotiable)

Use ONLY facts from the profile, corpus, and opportunity. Never invent personal
data (work authorization, addresses, identifiers) — mark gaps `[MISSING: …]`.

## Write-back contract (MUST)

- `mcp__app__save_artifact` — `title="Application kit — <organization> <role>"`,
  `kind="other"`, `opportunity_id` from the Opportunity block,
  `provenance="career-pack:apply-prep"`, `body` = the full kit markdown.
