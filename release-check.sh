#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VERSION="$(cat "$ROOT/VERSION")"
ERRORS=0

fail() { echo "FAIL: $1" >&2; ERRORS=$((ERRORS + 1)); }
ok()   { echo "OK:   $1"; }

echo "=== mq-agent release-check v${VERSION} ==="

# Tests
echo ""
echo "--- Tests ---"
if (cd "$ROOT" && uv run pytest tests/ -q --tb=no > /dev/null 2>&1); then
  ok "pytest"
else
  fail "pytest — run: uv run pytest tests/ -v"
fi

# Lint
echo ""
echo "--- Lint ---"
if (cd "$ROOT" && uv run ruff check mq_agent/ > /dev/null 2>&1); then
  ok "ruff"
else
  fail "ruff — run: uv run ruff check mq_agent/"
fi

# Docs consistency
echo ""
echo "--- Docs consistency ---"
if bash "$ROOT/scripts/check-docs-consistency.sh" > /dev/null 2>&1; then
  ok "check-docs-consistency.sh"
else
  bash "$ROOT/scripts/check-docs-consistency.sh" || true
  ERRORS=$((ERRORS + 1))
fi

# mqlaunch integration smoke
echo ""
echo "--- mqlaunch smoke ---"
if bash "$ROOT/scripts/smoke-mqlaunch.sh" > /dev/null 2>&1; then
  ok "smoke-mqlaunch.sh"
else
  bash "$ROOT/scripts/smoke-mqlaunch.sh" || true
  ERRORS=$((ERRORS + 1))
fi

# Summary
echo ""
if [[ "$ERRORS" -eq 0 ]]; then
  echo "=== All checks passed — ready to release v${VERSION} ==="
else
  echo "=== $ERRORS check(s) failed — fix before releasing ===" >&2
  exit 1
fi
