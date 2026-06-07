# Opportunity Hunter

A **local-first**, single-user web app for running a job hunt and a
business-opportunity hunt in parallel. It is the system of record (SQLite),
and it drives **locally-run Claude skills** (via the Claude Agent SDK) to do the
heavy lifting — with a chat + canvas UI you can reach from your phone over
Tailscale.

> Status: **Phase 0** — the vertical slice (skeleton + agent spine). See
> `~/.claude/plans/this-project-will-be-crispy-papert.md` for the full plan.

## Requirements

- **Python 3.10+** and [`uv`](https://docs.astral.sh/uv/)
- **Node 18+** (for the frontend build)
- **The Claude Code CLI** (`claude`) installed and authenticated — the Agent SDK
  drives it via a subprocess and reuses its auth. Check with `claude --version`.
  (Alternatively, set an Anthropic API key in Settings or `OH_ANTHROPIC_API_KEY`.)

## Layout

```
app/            FastAPI backend (API + serves the built frontend)
  agent/        Agent SDK runner + in-process MCP write-back tools
  routers/      /api endpoints (health, settings, chat, notes, runs)
frontend/       Next.js + Tailwind (chat + canvas); static export -> out/
tests/          pytest (deterministic layer; agent mocked)
data/           app.db (gitignored — your data; back it up)
```

## Run — development (hot reload)

Two processes; the frontend proxies `/api` to the backend.

```bash
# 1. backend (terminal A)
uv run uvicorn app.main:app --reload --port 8000

# 2. frontend (terminal B)
npm --prefix frontend run dev      # http://localhost:3000
```

## Run — daily use / phone over Tailscale (single process)

Build the frontend once; FastAPI then serves it and the API on one origin.

```bash
npm --prefix frontend install
NODE_ENV=production npm --prefix frontend run build   # -> frontend/out/
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open `http://<your-tailscale-hostname>:8000` from any device on your tailnet.
Binding to `0.0.0.0` (not `localhost`) is what makes it reachable from the phone.
The only "auth" is tailnet membership — fine for single-user.

## First run

1. Open the app, click the **Configure API key** badge (top-right). Either paste
   an Anthropic API key, or leave it blank to use the local `claude` CLI's auth.
2. In chat, try: *"Save a note titled 'Test' with body 'hello from the agent'."*
   The agent calls the `save_note` tool → a row lands in SQLite → it renders in
   the **canvas** pane.

## Tests

```bash
uv run pytest -q
```

Tests cover the deterministic layer (settings, the `save_note` write-back tool,
the permission gate, and the runner's persist/stream/replay) with the agent
mocked — no API key required.
