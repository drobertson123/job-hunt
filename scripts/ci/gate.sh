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

# --- 3. frontend lint (if deps installed) ----------------------------------
hdr "[3/3] frontend lint — npm run lint"
if [ -f "$ROOT/frontend/package.json" ]; then
  if [ -d "$ROOT/frontend/node_modules" ]; then
    if (cd "$ROOT/frontend" && npm run --silent lint); then pass "next lint"; else fail "next lint"; fi
  else
    skip "frontend/node_modules absent — skipping (enable: npm --prefix frontend install)"
  fi
else
  skip "no frontend/ — skipping"
fi

# --- summary ----------------------------------------------------------------
hdr "gate summary"
if [ ${#FAILED[@]} -eq 0 ]; then
  printf '  \033[32mGATE PASSED\033[0m\n'
  exit 0
fi
printf '  \033[31mGATE FAILED\033[0m: %s\n' "${FAILED[*]}"
exit 1
