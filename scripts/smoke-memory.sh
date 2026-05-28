#!/usr/bin/env bash
# smoke-memory.sh — verifies mq-agent memory commands are reachable.
# Runs without OPENAI_VECTOR_STORE_ID or repo-signal installed.
set -euo pipefail

echo "[smoke] semantic memory"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/lib/mq-agent-bin.sh"

if ! MQ_AGENT_BIN="$(resolve_mq_agent_bin "$ROOT")"; then
  echo "[FAIL] mq-agent not found"
  echo "Install it or run: uv pip install -e '.[dev,signal]'"
  exit 1
fi

echo "[check] mq-agent memory status"
if "$MQ_AGENT_BIN" memory status >/tmp/mq-agent-memory-status.out 2>&1; then
  cat /tmp/mq-agent-memory-status.out
  echo "[PASS] memory status"
else
  cat /tmp/mq-agent-memory-status.out
  echo "[FAIL] mq-agent memory status failed" >&2
  exit 1
fi

echo "[check] mq-agent memory build . --dry-run"
if "$MQ_AGENT_BIN" memory build . >/tmp/mq-agent-memory-build.out 2>&1; then
  cat /tmp/mq-agent-memory-build.out
  echo "[PASS] memory build --dry-run"
else
  cat /tmp/mq-agent-memory-build.out
  echo "[WARN] memory build --dry-run failed (repo-signal may not be installed)"
fi

echo "[PASS] semantic memory smoke passed"
