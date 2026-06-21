> Adapted from proficientlyjobs/proficiently-claude-skills (MIT). Concepts re-implemented for this project; no text copied.

# ATS Patterns Reference

A short field-layout guide for the three ATS platforms encountered most often.
This is preparation guidance for a human submitting an application — not
instructions for browser automation.

---

## Lever

**URL pattern:** `jobs.lever.co/{company}/{job-id}/apply`

**Difficulty:** Easy — a single native form, no account required.

**Key fields:**
- Full name, email address, phone number
- Location (free text or city/state)
- Resume upload (PDF recommended)
- Links: LinkedIn, GitHub, portfolio — each its own field
- "Additional information" text box — a good place to paste a cover letter
- EEO demographic survey (optional, presented at the end)

**Gotchas:** The links section is often hidden behind a "+" toggle; don't skip it.

---

## Greenhouse

**URL pattern:** Embedded form on the company's jobs page (cross-origin iframe).

**Difficulty:** Medium — embedded iframe can behave oddly in some browsers; the
form itself is straightforward once you reach it.

**Key fields:**
- First name and last name (separate fields)
- Email address, phone number
- Resume upload + optional cover-letter upload (separate fields)
- Location / city
- "How did you hear about us?" dropdown
- EEO questions and work-authorization questions (vary by company)

**Gotchas:** Cover letter is a separate upload, not a text box — prepare the file
in advance. Some companies add custom screening questions at the bottom.

---

## Workday

**URL pattern:** `{company}.wd{n}.myworkdayjobs.com` or `{company}.myworkdayjobs.com`

**Difficulty:** Hard — multi-step wizard, requires creating or signing into a
Workday account before you can save progress.

**Pages (in order):**
1. My Information — name, contact details, location, work authorization
2. My Experience — resume upload, work history, education (may auto-parse resume)
3. Application Questions — company-specific screening questions
4. Voluntary Disclosures — veteran status, disability
5. Self Identify — EEO fields
6. Review — final check before submit

**Gotchas:** Create your Workday account before starting so you don't lose
progress. "Autofill with Resume" parses your PDF but always review the
extracted fields — it frequently mis-parses dates and job titles.
