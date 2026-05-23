#!/usr/bin/env bash
# Install smoke test — verifies mq-agent is usable after install.
set -euo pipefail

echo "=== mq-agent install smoke test ==="

echo "--- help ---"
mq-agent --help > /dev/null

echo "--- doctor ---"
mq-agent doctor || true   # passes even without OPENAI_API_KEY

echo "--- tools ---"
mq-agent tools > /dev/null

echo "--- score ---"
mq-agent score . > /dev/null

echo "--- repo-summary ---"
mq-agent repo-summary . > /dev/null

echo "=== smoke test passed ==="
