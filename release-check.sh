#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VERSION="$(cat "$ROOT/VERSION")"
ERRORS=0

export UV_CACHE_DIR="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/mq-agent-uv-cache}"

# Handles fail.
fail() { echo "FAIL: $1" >&2; ERRORS=$((ERRORS + 1)); }
# Handles ok.
ok()   { echo "OK:   $1"; }

echo "=== mq-agent release-check v${VERSION} ==="

# Version lock
echo ""
echo "--- Version lock ---"
LOCK_VERSION="$(awk '
  $0 == "[[package]]" { in_package=1; name=""; version=""; next }
  in_package && /^name = "mq-agent"/ { name="mq-agent"; next }
  in_package && /^version = / { version=$3; gsub("\"", "", version); next }
  in_package && /^source = .*editable = "."/ && name == "mq-agent" {
    print version
    exit
  }
' "$ROOT/uv.lock")"

if [[ "$LOCK_VERSION" == "$VERSION" ]]; then
  ok "uv.lock package version matches VERSION ($VERSION)"
else
  fail "uv.lock mq-agent version '$LOCK_VERSION' != VERSION '$VERSION'"
fi

# Tests
echo ""
echo "--- Tests ---"
if (cd "$ROOT" && uv run --extra dev --extra signal pytest tests/ -q --tb=no > /dev/null 2>&1); then
  ok "pytest"
else
  fail "pytest — run: uv run --extra dev --extra signal pytest tests/ -v"
fi

# Lint
echo ""
echo "--- Lint ---"
if (cd "$ROOT" && uv run --extra dev ruff check mq_agent/ > /dev/null 2>&1); then
  ok "ruff"
else
  fail "ruff — run: uv run --extra dev ruff check mq_agent/"
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

# Skill contracts
echo ""
echo "--- Skill contracts ---"
if bash "$ROOT/scripts/check-skill-contracts.sh" > /dev/null 2>&1; then
  ok "check-skill-contracts.sh"
else
  bash "$ROOT/scripts/check-skill-contracts.sh" || true
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

# Memory smoke
echo ""
echo "--- memory smoke ---"
if bash "$ROOT/scripts/smoke-memory.sh" > /dev/null 2>&1; then
  ok "smoke-memory.sh"
else
  bash "$ROOT/scripts/smoke-memory.sh" || true
  ERRORS=$((ERRORS + 1))
fi

# Summary
echo ""
if [[ "$ERRORS" -eq 0 ]]; then
  echo "=== All checks passed — ready to release v${VERSION} ==="
  echo "Next: push a release-prep branch, open a PR, wait for CI, then tag from merged main."
else
  echo "=== $ERRORS check(s) failed — fix before releasing ===" >&2
  exit 1
fi
