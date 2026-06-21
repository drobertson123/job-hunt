> Adapted from proficientlyjobs/proficiently-claude-skills (MIT). Concepts re-implemented for this project; no text copied.

# Fit-Scoring Rubric

## Purpose

The fit-scoring rubric gives the candidate a fast, honest triage signal for
every opportunity in the pipeline. It answers "should I spend time on this?"
before any CV tailoring or outreach work begins.

## How the rubric works

Evaluation proceeds in priority order — each tier gates the next:

1. **Dealbreakers** — conditions that make a role categorically wrong regardless
   of its other merits (e.g., required relocation to an unwanted city, a company
   type the candidate refuses). If the opportunity matches even one dealbreaker,
   the analysis stops and the rating is **Skip**. No further scoring is performed.

2. **Must-haves** — conditions that the candidate requires for a role to be worth
   pursuing (e.g., remote-eligible, staff-level or above). The analysis counts
   how many are satisfied. Most unmet → **Low**. All met → proceed to the next
   tier.

3. **Nice-to-haves** — desirable but not essential conditions (e.g., equity,
   specific tech stack). Used to distinguish **High** from **Medium** when
   must-haves are clear.

## Rating mapping

| Rating   | Condition                                                              |
|----------|------------------------------------------------------------------------|
| **High** | No dealbreakers + all must-haves met + at least two nice-to-haves     |
| **Medium** | No dealbreakers + most or all must-haves met, few nice-to-haves      |
| **Low**  | No dealbreakers but significant must-have gaps                         |
| **Skip** | Any dealbreaker matched                                                |

If the candidate has set no preferences, the skill infers reasonable defaults
from the synthesized profile and corpus, and notes that it did so.

## Pipeline integration

The rating drives the decision record saved by `mcp__app__record_decision`.
The summary format `<Rating> · Fit <score>/5 — <verdict>: <role> @ <org>`
means the attention dashboard and opportunity list can surface Skip entries
without the user opening each one.
