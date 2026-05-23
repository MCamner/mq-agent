#!/usr/bin/env bash
# smoke-mqlaunch.sh — verifies all commands that mqlaunch calls via mq-agent-menu.sh.
# Runs without a live mqlaunch session or OPENAI_API_KEY.
set -euo pipefail

AGENT_DIR="${MQ_AGENT_BIN:-$HOME/mq-agent}"
ERRORS=0

run() { (cd "$AGENT_DIR" && uv run mq-agent "$@"); }
ok()   { echo "OK:   $1"; }
fail() { echo "FAIL: $1" >&2; ERRORS=$((ERRORS + 1)); }

echo "=== mq-agent mqlaunch bridge smoke test ==="

echo ""
echo "--- REPO ANALYSIS (no API key) ---"

run score . > /dev/null 2>&1        && ok "score ."           || fail "score ."
run repo-summary . > /dev/null 2>&1 && ok "repo-summary ."    || fail "repo-summary ."
run tools > /dev/null 2>&1          && ok "tools"             || fail "tools"
run tools --json > /dev/null 2>&1   && ok "tools --json"      || fail "tools --json"

echo ""
echo "--- ENVIRONMENT ---"

# doctor always exits 0 — it shows FAIL rows but doesn't error out
run doctor > /dev/null 2>&1         && ok "doctor"            || fail "doctor"

echo ""
echo "--- MCP LOCAL TOOLS (mq-mcp not required) ---"

# mcp status exits 0 whether or not mq-mcp is running
run mcp status --json > /dev/null 2>&1  && ok "mcp status --json"  || fail "mcp status --json"

# tools --describe works offline (name-prefix classification)
run tools --describe read_repo_file --json > /dev/null 2>&1 \
  && ok "tools --describe read_repo_file --json" \
  || fail "tools --describe read_repo_file --json"

# run-tool dry-run requires no server
run run-tool read_repo_file --dry-run --json > /dev/null 2>&1 \
  && ok "run-tool read_repo_file --dry-run" \
  || fail "run-tool read_repo_file --dry-run"

echo ""
if [[ "$ERRORS" -eq 0 ]]; then
  echo "=== All mqlaunch bridge checks passed ==="
else
  echo "=== $ERRORS check(s) failed ===" >&2
  exit 1
fi
