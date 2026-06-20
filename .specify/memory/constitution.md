<!--
SYNC IMPACT REPORT
==================
Version change: 1.1.0 → 1.2.0
Bump rationale: MINOR — expanded Principle IV pipeline (added validate → review →
                revise/resolve → PR stages) and added Push-Authority rules (human-only
                main; agents may PR/push green changes to develop).

--- 1.1.0 ---
Version change: 1.0.0 → 1.1.0
Bump rationale: MINOR — added new Git workflow guidance (Gitflow branching model +
                mandatory git worktree isolation) to Development Workflow & Quality Gates.

--- 1.0.0 (initial ratification) ---
Version change: (template, unratified) → 1.0.0
Bump rationale: Initial ratification — placeholders replaced with concrete principles
                derived from established project practice.

Modified principles: (none — first ratification)
Added principles:
  - I. Local-First, SQLite Is the System of Record
  - II. Agent Write-Back Through Typed Tools
  - III. Grounded, Human-Approved Output (NON-NEGOTIABLE)
  - IV. Spec-Driven & Test-First (NON-NEGOTIABLE)
  - V. Vertical Slices & Ruthless Simplicity (YAGNI)
Added sections:
  - Technology & Architecture Constraints
  - Development Workflow & Quality Gates

Templates requiring updates:
  ✅ .specify/templates/plan-template.md — Constitution Check gate is generic
       ([Gates determined based on constitution file]); no edit needed.
  ✅ .specify/templates/spec-template.md — no constitution references; no edit needed.
  ✅ .specify/templates/tasks-template.md — no constitution references; no edit needed.

Follow-up TODOs: none. RATIFICATION_DATE set to constitution authoring date (2026-06-20);
  revise if an earlier formal adoption date is preferred.
-->

# Opportunity Hunter Constitution

## Core Principles

### I. Local-First, SQLite Is the System of Record

The SQLite database is the single durable source of truth. All meaningful state —
opportunities, actions, artifacts, decisions, corpus, profile, and their relations —
MUST be persisted as normalized rows. The app is local-first and single-user: it runs
on the user's machine, reachable from their devices over Tailscale, and MUST NOT depend
on a hosted multi-tenant backend to function. Agent sessions, request handlers, and UI
state are ephemeral; if a fact matters after the process exits, it lives in SQLite.

Rationale: A personal job/opportunity hunt is long-running and private. Durability and
data sovereignty come from owning the database, not from any one process staying alive.

### II. Agent Write-Back Through Typed Tools

Agents are ephemeral workers, never the source of truth. Every agent-driven mutation MUST
flow through an in-process MCP write-back tool that calls a service function which writes
the normalized schema (e.g. `save_opportunity`, `record_action`, `save_artifact`). Agents
MUST NOT write the database by any other path. Service functions own validation,
deduplication (idempotent upsert on `dedupe_key`/`content_hash`), and provenance
(`run_id`). Shared core columns plus a typed `details` JSON column keep the job and
business tracks in one schema without sparse columns.

Rationale: A typed write-back seam is the crux that lets stochastic agents safely populate
a deterministic store, and keeps the schema the contract between agent and app.

### III. Grounded, Human-Approved Output (NON-NEGOTIABLE)

Generated deliverables that represent the user (CVs, cover letters, outreach, proposals,
pitches) MUST be grounded against the user's own corpus and MUST pass a human approval
gate before they can be exported or sent. The pipeline is fixed: generate → grounding
check (flag unsupported sentences) → `needs_review` → explicit human `approve` → export.
Export of a generative artifact in a non-approved state MUST be refused. Fabricated or
unverifiable claims MUST NOT leave the system.

Rationale: The product's trust hinges on never putting invented facts in front of an
employer under the user's name. The gate is a feature, not friction.

### IV. Spec-Driven & Test-First (NON-NEGOTIABLE)

Non-trivial work follows the full cycle: brainstorm → spec → plan → tasks → TDD →
implement → validate → review → revise/resolve → PR. Every feature or bugfix is built
test-first: write a failing test, see it fail, then implement to green, then refactor.
Validation, review, and resolution of review feedback all precede the PR. Tests MUST be deterministic by default; calls to external LLM/embedding
APIs are stubbed in unit tests and exercised only behind explicitly key-gated live probes.
No feature is "done" until its verification command has been run and its passing output
observed — claims of success without observed evidence are prohibited.

Rationale: Agent-built code at speed is only safe when behavior is pinned by tests and
intent is pinned by a spec the user approved first.

### V. Vertical Slices & Ruthless Simplicity (YAGNI)

Work ships as complete vertical slices — schema, service, agent tool/API, and UI as
needed — that are independently testable and demonstrably working end-to-end, rather than
broad horizontal layers left unwired. Prefer the simplest schema and code that satisfies
the current slice; reuse the existing migration primitive (`create_all` for new tables,
`_ensure_column` for new columns) over heavyweight tooling. Speculative generality,
unused abstraction, and features no current slice needs MUST be omitted.

Rationale: Thin end-to-end slices keep the system always-demonstrable and prevent the
backend/UI drift that accrues when layers are built ahead of their consumers.

## Technology & Architecture Constraints

- **Stack**: FastAPI backend serving the API and the built Next.js/React/Tailwind static
  export from a single origin (`0.0.0.0:8000`). Python 3.12 managed with `uv`.
- **LLM split**: OpenAI provides embeddings (RAG/grounding); Claude provides reasoning and
  skills via the Claude Agent SDK. Default agent model is Sonnet (`claude-sonnet-4-6`);
  Opus is reserved for deep analysis. Model choice is per-task configurable in Settings.
- **Secrets**: API keys are user-supplied (Settings or environment) and MUST NOT be
  committed. Code MUST degrade gracefully (skip/clearly error) when a key is absent.
- **Concurrency**: Concurrent agent runs MUST NOT corrupt or cross-attribute state;
  write-back is attributed to its `run_id` and verified safe under concurrency.
- **Access**: Reachable from the user's phone over Tailscale; no public exposure assumed.

## Development Workflow & Quality Gates

- **Design gate**: Creative/behavioral changes start with the brainstorming flow and a
  written, user-approved spec under `docs/superpowers/specs/` or `.specify/` before code.
- **Execution**: Plans are executed via subagent-driven development — Sonnet implementers
  with Opus reviewers — following the approved task list.
- **Constitution Check**: Each plan MUST evaluate itself against these principles in its
  Constitution Check section; violations MUST be justified in Complexity Tracking or the
  approach revised.
- **Verification before completion**: Run the relevant tests/build and observe passing
  output before claiming completion, committing, or opening a PR.
- **Branching (Gitflow)**: `main` holds stable, release-ready history; `develop` is the
  integration branch. Feature work branches as `feature/<name>` off `develop` and merges
  back to `develop`; releases cut `release/<version>` (merged to `main` and back to
  `develop`, tagged); urgent fixes use `hotfix/<name>` off `main` (merged to both). Change
  arrives via a branch merge, never a direct commit to a long-lived branch.
- **Push authority**: `main` is the master/release branch — only the human may push to
  `main`; agents MUST NOT push to or merge into `main`. `develop` is the development
  integration branch — agents MAY open PRs against `develop` and push to it, but ONLY when
  the change fully passes the test suite and all quality checks. A red or unverified change
  MUST NOT be pushed.
- **Worktree isolation**: Each feature/release/hotfix branch is developed in its own git
  worktree, never by switching branches in the primary checkout. This keeps the main
  workspace clean, enables parallel slices without cross-contamination, and matches the
  ephemeral-worker model — an isolated worktree per unit of work.
- **Review & integration**: Changes are code-reviewed before the branch merges. Within the
  push-authority rules above, agents may push green branches and open PRs against `develop`
  autonomously; merges into `main` are reserved to the human.

## Governance

This constitution supersedes other development practices for this project where they
conflict; the user's explicit instructions supersede the constitution. Amendments are made
by editing this file with a rationale and a version bump, and re-running any dependent
template sync. Versioning is semantic: MAJOR for backward-incompatible
principle removals or redefinitions, MINOR for a new principle or materially expanded
guidance, PATCH for clarifications and non-semantic refinements. All plans and reviews are
expected to verify compliance with the principles above; unavoidable deviations MUST be
documented and justified, not silently adopted.

**Version**: 1.2.0 | **Ratified**: 2026-06-20 | **Last Amended**: 2026-06-20
