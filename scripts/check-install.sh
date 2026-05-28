#!/usr/bin/env bash
# Install smoke test — verifies mq-agent is usable after install.
set -euo pipefail

echo "=== mq-agent install smoke test ==="

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/lib/mq-agent-bin.sh"

if ! MQ_AGENT_BIN="$(resolve_mq_agent_bin "$ROOT")"; then
  echo "FAIL: mq-agent not found"
  echo "Install it or run: uv pip install -e '.[dev,signal]'"
  exit 1
fi

echo "--- help ---"
"$MQ_AGENT_BIN" --help > /dev/null

echo "--- doctor ---"
"$MQ_AGENT_BIN" doctor || true   # passes even without OPENAI_API_KEY

echo "--- tools ---"
"$MQ_AGENT_BIN" tools > /dev/null

echo "--- score ---"
"$MQ_AGENT_BIN" score . > /dev/null

echo "--- repo-summary ---"
"$MQ_AGENT_BIN" repo-summary . > /dev/null

echo "=== smoke test passed ==="
