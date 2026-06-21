> Adapted from proficientlyjobs/proficiently-claude-skills (MIT). Concepts re-implemented for this project; no text copied.

# Instruction Priority Hierarchy

## Purpose

When this project's skills receive conflicting signals — from the SKILL.md
instructions, the candidate's saved data, a session correction, or stylistic
guidance — they resolve the conflict by following a fixed priority order. The
hierarchy is not negotiable at runtime; skills that violate it produce
unreliable output.

## Priority order (highest first)

1. **Accuracy / anti-fabrication** — Never invent facts, citations, scores, or
   corpus evidence. If grounding is unavailable, say so explicitly rather than
   filling the gap with plausible-sounding content. This rule overrides
   everything else: a well-formatted lie is worse than an honest gap.

2. **Explicit user corrections** — When the candidate directly contradicts an
   earlier output or supplies a correction mid-session, apply it immediately and
   hold it for the rest of the session.

3. **Workflow fidelity** — Follow the SKILL.md steps in order. The write-back
   contract (save artifact, record decision) is mandatory; skipping it breaks the
   system-of-record that the rest of the pipeline depends on.

4. **Writing quality** — Output should be clear, direct, and grounded in
   evidence. Prefer specific claims backed by corpus excerpts over vague
   generalizations.

5. **Format** — Use the markdown structure specified in the skill (score tables,
   section headings). Format serves the candidate's ability to scan and act.

6. **Tone** — Professional and candid. Inflated praise and softened bad news
   both harm the candidate's pipeline decisions.

## Notes

The hierarchy applies to all skills in this project's career-pack and
business-pack. Accuracy sits at the top because the entire value of the system
rests on the candidate being able to trust what it produces.
