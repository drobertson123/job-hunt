# Changelog

## 1.0.0 — 2026-06-21

The first complete release of **Opportunity Hunter** — a local-first, single-user
job- and opportunity-hunt app: SQLite is the system of record, the local `claude`
CLI (via the Claude Agent SDK) does the reasoning/skills through typed MCP
write-back tools, and a FastAPI backend serves the built Next.js UI on one origin.

### Capabilities (career + business packs)
- Corpus-grounded **cover letters**, **CV tailoring**, **fit analysis** (now with
  a decisive dealbreakers → must-haves → nice-to-haves rubric), **interview prep**,
  **company research/enrich**, **opportunity enrich**, and business-track discovery.
- **email-analyser** / **sms-analyser** — paste a message → logged Communication +
  follow-up Action.
- **network-scan** — warm-intro openings at companies where you know someone.
- **apply-prep** — ATS-aware application kit (no browser automation).
- **content-library** — synthesize reusable headline/summary/bullet variants from
  your corpus; `cv-tailor` reuses them.

### Integrations
- **Inbound message webhook** (`POST /api/communications/inbound`, + `/sms`) — any
  channel (sms / whatsapp / linkedin / …); untriaged messages surface in Attention.
  Android notification-forwarding recipe in `docs/sms-forwarding-android.md`.
- **Google** (OAuth2 foundation; one consent covers all): **Gmail** ingest →
  Communications, **Calendar** two-way (push interviews), **Contacts** two-way
  (import + push). Setup guide in `docs/google-setup.md`.

### Process engine
- **Job preferences** (dealbreakers / must-haves / nice-to-haves) driving fit
  scoring and triage.
- **Daily job-search scheduler** (opt-in per source) + **weekly identify → apply →
  follow-up** review.
- **Interview calendar** with `.ics` export.
- **Persistent Claude CLI session** (warm, reconnecting, keep-alive).

### UI — the "Job Hunter" design
- Warm-cream + indigo theme (Figtree / JetBrains Mono), a 76px icon nav rail, a
  greeting top bar, and a **resizable right-edge AI assistant drawer**.
- Screens: **Board** (kanban + auto-discovery strip + resizable insight rail),
  rebuilt **Detail** (stage stepper, automation panel), **Companies**, **Contacts**,
  **Metrics** (funnel + volume + sources), **Documents**, **Automations**,
  **Relationships** (warm-intro network), plus Workspace / Profile / Library /
  Applications / Interviews / Sources / This-week / Attention.
- Markdown raw↔rendered views; grounding/approval gate on generative artifacts.

### Foundations
- Gitflow + worktree isolation; local-only quality gate (`scripts/ci/gate.sh`).
- 290 tests passing; all external services (Claude CLI, OpenAI, Google) are
  injected/stubbed in tests and exercised live behind key-gated probes.
- Attribution: parts of the job-hunt **work processes** adapt concepts from
  `proficientlyjobs/proficiently-claude-skills` (MIT) — see `ATTRIBUTION.md`
  (concepts re-implemented on this project's architecture; no text copied).

### Notes
- Google integrations require a one-time Google Cloud setup to go live.
- The frontend is verified by `next build` + a backend test suite; there is no
  frontend unit-test harness yet.
