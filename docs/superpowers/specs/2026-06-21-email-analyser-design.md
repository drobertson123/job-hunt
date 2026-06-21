# Email Analyser — Design

## Goal
Let the user paste an email about an opportunity and have the agent extract its
meaning and record it in the tracker: an inbound **Communication** linked to the
opportunity, plus a follow-up **Action** when the email asks the user to do
something. No fabrication — only facts present in the email.

## Approach (fits the existing capability pattern)
An authored **career-pack capability** `email-analyser`, structurally identical
to `enrich-opportunity` (paste text → write structured rows through existing MCP
tools). It is NOT generative: it writes `Communication`/`Action` rows via
`mcp__app__record_communication` and `mcp__app__record_action`, so it needs no
artifact/grounding/approval pipeline.

- `requires_opportunity = True` — the user selects which opportunity the email
  concerns (reliable linking; the opportunity `id` is inlined in the prompt via
  `opportunity_block`, so no fuzzy matching or new read-tool is required).
- `requires_input = True` — the pasted raw email.
- `include_profile = False`.

## Behavior (skill)
1. Read the Opportunity block (note `id`) and the Input email.
2. `record_communication`: direction (`inbound` default), channel `email`,
   `opportunity_id`, `subject`, a faithful `body` summary, `occurred_at` (if the
   email shows a date), `thread_key`, and `follow_up_due_at` ONLY when a reply-by
   date is stated/clearly implied.
3. `record_action` when a next step is needed (reply / schedule / send docs /
   prep / decide), with any interview date/time quoted verbatim in `detail` and
   `due_at` only if a date is given. If nothing is required (plain rejection/FYI)
   it logs only the communication and says so.
4. Anti-fabrication: never invent dates, names, or follow-ups not in the email.

Calendar event creation is OUT of scope here (that is goal item #6); this slice
captures interview dates into the Action `detail` so #6 can consume them.

## Files
- Create `skills/career-pack/skills/email-analyser/SKILL.md` (frontmatter
  `name: email-analyser`; a `## Write-back contract` section naming the two
  `mcp__app__` tools).
- Add a `Capability(name="email-analyser", …)` entry to `app/capabilities.py`.
- Update test expectations: `EXPECTED_SKILLS` set + three `== 11 → 12` counts +
  the `by_name` set in `test_capabilities_api.py`.

## Testing
The existing static-validity suite IS the spec: `test_career_pack.py`
(EXPECTED_SKILLS membership, frontmatter name match, `## Write-back contract` +
`mcp__app__` present, skill count), `test_capabilities.py` (SKILL_NAMES count),
`test_capabilities_api.py` (capability list + count). No new backend behavior;
gate (`scripts/ci/gate.sh`) must stay green. Constitution II (typed write-back)
honored — the agent writes only through existing tools.
