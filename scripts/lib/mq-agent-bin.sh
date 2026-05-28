#!/usr/bin/env bash

# Resolve the mq-agent executable for smoke scripts.
resolve_mq_agent_bin() {
  local root="${1:-$(pwd)}"

  if [[ -n "${MQ_AGENT_BIN:-}" ]]; then
    printf '%s\n' "$MQ_AGENT_BIN"
    return 0
  fi

  if command -v mq-agent >/dev/null 2>&1; then
    command -v mq-agent
    return 0
  fi

  if [[ -x "$root/.venv/bin/mq-agent" ]]; then
    printf '%s\n' "$root/.venv/bin/mq-agent"
    return 0
  fi

  return 1
}
