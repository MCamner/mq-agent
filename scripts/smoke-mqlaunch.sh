#!/usr/bin/env bash
# smoke-mqlaunch.sh — verifies mqlaunch can reach mq-agent.
# Runs without a live mqlaunch session or OPENAI_API_KEY.
set -euo pipefail

TMPDIR="${TMPDIR:-/tmp}"

# Runs check.
run_check() {
  local label="$1"
  shift
  local outfile="$TMPDIR/mq-agent-${label//[^A-Za-z0-9_-]/-}.out"

  echo "[check] mqlaunch agent $label"
  if mqlaunch agent "$@" > "$outfile" 2>&1; then
    echo "[PASS] mqlaunch can call mq-agent $label"
  else
    cat "$outfile"
    echo "[FAIL] mqlaunch agent $label failed" >&2
    exit 1
  fi
}

echo "[smoke] mqlaunch integration"

if ! command -v mqlaunch >/dev/null 2>&1; then
  echo "[SKIP] mqlaunch not found"
  echo "Install or link macos-scripts first:"
  echo "  cd ~/macos-scripts && ./install.sh"
  exit 0
fi

run_check doctor doctor
run_check score score .
run_check repo-summary repo-summary .
run_check release-workflow release-workflow --json

echo "[check] mqlaunch agent mcp-status"
if mqlaunch agent mcp-status > "$TMPDIR/mq-agent-mcp-status.out" 2>&1; then
  echo "[PASS] mqlaunch can call mq-agent mcp status"
else
  cat "$TMPDIR/mq-agent-mcp-status.out"
  echo "[FAIL] mqlaunch agent mcp-status failed" >&2
  exit 1
fi

echo "[PASS] mqlaunch integration smoke passed"
