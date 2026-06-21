# Attribution

Parts of this project's job-hunt **work processes** are adaptations of concepts
from **[proficientlyjobs/proficiently-claude-skills](https://github.com/proficientlyjobs/proficiently-claude-skills)** (MIT License), by Proficiently.

We re-implemented the *concepts* against this project's own architecture (SQLite
system-of-record, in-process MCP write-back tools, corpus grounding) and local
storage — **no source text was copied**. Adapted concepts include:

- The **fit-scoring rubric** (dealbreakers → must-haves → nice-to-haves →
  High/Medium/Low/Skip) — see `skills/career-pack/skills/fit-analysis/SKILL.md`
  and `docs/references/fit-scoring.md`.
- The **job-preferences** model (dealbreakers / must-haves / nice-to-haves),
  stored on the `Profile` row rather than a `preferences.md` file.
- The **instruction priority hierarchy** — see `docs/references/priority-hierarchy.md`.
- **network-scan** (warm-intro company scan) and **apply-prep** (ATS-aware application kit) — see the career-pack skills and `docs/references/ats-patterns.md`.

Original project: https://github.com/proficientlyjobs/proficiently-claude-skills ·
Proficiently: https://proficiently.com
