#!/usr/bin/env bash
#
# Point git at the version-controlled hooks in .githooks/.
# Run once per clone (and once per linked worktree shares the same config).
#
#   scripts/install-hooks.sh
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
git config core.hooksPath .githooks
echo "core.hooksPath -> .githooks (pre-push gate active)."
