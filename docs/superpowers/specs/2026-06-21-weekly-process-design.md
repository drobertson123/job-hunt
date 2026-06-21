# Weekly Process (Identify → Apply → Follow-up) — Design

## Goal
A repeatable weekly ritual that, from current pipeline state, surfaces exactly
what to do this week across the three job-hunt phases — **identify** new
opportunities, **apply** to qualified ones, **follow up** on in-flight ones —
and can materialize those into actionable tasks in one click.

## Approach (deterministic, no agent)
A pure server-side service over the DB — reliable and testable, unlike an agent
turn. It buckets non-terminal opportunities by their existing `PipelineStage`:

| Bucket | Stages | Meaning |
|---|---|---|
| `to_identify` | `new` | freshly surfaced (incl. daily-search finds) — triage: pursue or drop |
| `to_apply` | `qualifying`, `analyzing` — minus any opp that already has an `Application` | decided to pursue, not yet applied |
| `to_follow_up` | `active`, `in_dialogue` | applied / interviewing — chase a response |

`won`/`lost` are terminal and excluded from every bucket. Also returns
`interviews_this_week` (InterviewEvents in `[now, now+7d]`).

This complements the existing **attention** dashboard (staleness/overdue alerts):
attention says "what's overdue right now"; the weekly review frames the whole
week's identify→apply→follow-up worklist.

## Service — `app/weekly_review.py`
- `weekly_review(session, *, now=None) -> dict` → `{to_identify, to_apply,
  to_follow_up, interviews_this_week, counts}`. Each opp rendered as
  `{id, title, organization, stage, type}`; interviews as
  `{id, title, starts_at, opportunity_id}`. `now` injected for deterministic tests.
- `create_weekly_actions(session, *, now=None) -> {created: int}` → for each
  bucket item lacking an OPEN action of the matching kind for that opportunity,
  create one Action: identify→`research` "Triage: {title}", apply→`apply`
  "Apply: {title}", follow_up→`followup` "Follow up: {title}". Idempotent —
  re-running does not duplicate. Creates Action rows directly (NOT via
  `add_action`) so planning does not bump `last_activity_at` and falsely reset
  staleness.

## API — `app/routers/weekly.py`
- `GET /api/weekly-review` → the plan.
- `POST /api/weekly-review/actions` → materialize → `{created}`.
Registered in `app/main.py`.

## UI — `frontend/app/components/WeeklyTab.tsx`
A new "This week" canvas tab: three labeled bucket columns/sections
(Identify / Apply / Follow up) listing opportunities (click → detail tab), an
"Interviews this week" strip, the counts, and a "Create this week's actions"
button (POST then show "{n} actions created"). `api.ts` gains
`fetchWeeklyReview`/`createWeeklyActions`. Wired into `page.tsx` (canvas union,
nav button, render branch with the standard `onOpen → detail` handler).

## Testing
- `weekly_review`: opps seeded across stages → correct bucketing; `won`/`lost`
  excluded; a `qualifying` opp WITH an Application is dropped from `to_apply`;
  interviews filtered to the 7-day window; counts match.
- `create_weekly_actions`: creates the right kinds/titles; re-running creates 0
  (idempotent); does not touch `last_activity_at`.
- API: GET shape + POST `{created}`.
- Frontend: `next build`.
Gate green. Constitution II honored — actions written through the service layer.
