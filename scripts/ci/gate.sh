#!/usr/bin/env bash
#
# Local quality gate — the authoritative pre-merge check for this repo.
#
# Per the project constitution (Local-only quality gates): all testing and
# quality checks run LOCALLY and MUST pass before code is committed/pushed to
# the repository. This project does NOT use GitHub Actions or any hosted CI;
# this script (and the pre-push hook that calls it) is the gate.
#
# Usage:
#   scripts/ci/gate.sh           # run every gate; non-zero exit on any failure
#
# Checks (in order):
#   1. Backend tests  — pytest                 (REQUIRED; blocks)
#   2. Backend lint   — ruff                    (blocks if ruff is installed; skipped otherwise)
#   3. Frontend lint  — npm run lint            (blocks if frontend deps installed; skipped otherwise)
#
# Worktree-aware: when run from a git worktree without its own .venv, it falls
# back to the primary checkout's .venv for the interpreter, while testing the
# CURRENT checkout's code.
set -uo pipefail

# --- locate repo root + python interpreter ---------------------------------
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "not in a git repo"; exit 1; }
cd "$ROOT"

PY=""
if [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
else
  # In a linked worktree .venv lives in the primary checkout; fall back to it.
  MAIN_ROOT="$(dirname "$(cd "$(git rev-parse --git-common-dir)" && pwd -P)")"
  if [ -x "$MAIN_ROOT/.venv/bin/python" ]; then
    PY="$MAIN_ROOT/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
  fi
fi
[ -n "$PY" ] || { echo "no python interpreter found (.venv or python3)"; exit 1; }

FAILED=()
pass() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; FAILED+=("$1"); }
skip() { printf '  \033[33m–\033[0m %s\n' "$1"; }
hdr()  { printf '\n\033[1m%s\033[0m\n' "$1"; }

# --- 1. backend tests (required) -------------------------------------------
hdr "[1/3] backend tests — pytest"
if "$PY" -m pytest -q; then pass "pytest"; else fail "pytest"; fi

# --- 2. backend lint (ruff, if available) ----------------------------------
hdr "[2/3] backend lint — ruff"
if "$PY" -m ruff --version >/dev/null 2>&1; then
  if "$PY" -m ruff check .; then pass "ruff check"; else fail "ruff check"; fi
elif command -v ruff >/dev/null 2>&1; then
  if ruff check .; then pass "ruff check"; else fail "ruff check"; fi
else
  skip "ruff not installed — skipping (enable: uv add --dev ruff)"
fi

# --- 3. frontend lint (only when deps installed AND eslint is configured) --
# `next lint` prompts interactively when no ESLint config exists; a gate must
# never block on a prompt, so we run it only once a real config is present.
hdr "[3/3] frontend lint — npm run lint"
FE="$ROOT/frontend"
eslint_configured() {
  ls "$FE"/.eslintrc* "$FE"/eslint.config.* >/dev/null 2>&1 && return 0
  grep -q '"eslintConfig"' "$FE/package.json" 2>/dev/null
}
if [ ! -f "$FE/package.json" ]; then
  skip "no frontend/ — skipping"
elif [ ! -d "$FE/node_modules" ]; then
  skip "frontend/node_modules absent — skipping (enable: npm --prefix frontend install)"
elif ! eslint_configured; then
  skip "no ESLint config in frontend/ — skipping (set up: npm --prefix frontend run lint)"
else
  # </dev/null guards against any tool reading stdin and hanging the hook.
  if (cd "$FE" && npm run --silent lint </dev/null); then pass "next lint"; else fail "next lint"; fi
fi

# --- summary ----------------------------------------------------------------
hdr "gate summary"
if [ ${#FAILED[@]} -eq 0 ]; then
  printf '  \033[32mGATE PASSED\033[0m\n'
  exit 0
fi
printf '  \033[31mGATE FAILED\033[0m: %s\n' "${FAILED[*]}"
exit 1
