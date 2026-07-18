#!/usr/bin/env bash
# Canonical repo releasability check. Read-only.
#
# Human mode (no flags): prints per-check OK/FAIL, exits 1 on any failure.
# Contract mode (--json): emits a repo_release_check.v1 object on stdout and
#   exits 0 (the `status` field carries the verdict). Consumed by mq-agent's
#   `stack release --all --preflight`.
# --dry-run is accepted for contract compatibility; this check never mutates,
#   so it is a no-op here.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VERSION="$(cat "$ROOT/VERSION")"

JSON=0
for arg in "$@"; do
  case "$arg" in
    --json) JSON=1 ;;
    --dry-run) : ;;
    *) ;;
  esac
done

export UV_CACHE_DIR="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/mq-agent-uv-cache}"

BLOCKERS=()

say()  { [[ "$JSON" -eq 1 ]] || echo "$1"; }
ok()   { [[ "$JSON" -eq 1 ]] || echo "OK:   $1"; }
fail() { BLOCKERS+=("$1"); [[ "$JSON" -eq 1 ]] || echo "FAIL: $1" >&2; }

# run_check LABEL CMD...  — records a blocker on non-zero exit; keeps stdout
# clean in JSON mode by routing captured output to stderr only.
run_check() {
  local label="$1"; shift
  local out
  if out="$("$@" 2>&1)"; then
    ok "$label"
  else
    fail "$label"
    [[ "$JSON" -eq 1 ]] || printf '%s\n' "$out" >&2
  fi
}

say "=== mq-agent release-check v${VERSION} ==="

# Version lock
say ""
say "--- Version lock ---"
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

say ""
say "--- Tests ---"
run_check "pytest" uv run --extra dev --extra signal pytest tests/ -q --tb=no

say ""
say "--- Lint ---"
run_check "ruff" uv run --extra dev ruff check mq_agent/

say ""
say "--- Docs consistency ---"
run_check "check-docs-consistency.sh" bash "$ROOT/scripts/check-docs-consistency.sh"

say ""
say "--- Skills consistency ---"
run_check "check-skills.sh" bash "$ROOT/scripts/check-skills.sh"

say ""
say "--- mqlaunch smoke ---"
run_check "smoke-mqlaunch.sh" bash "$ROOT/scripts/smoke-mqlaunch.sh"

say ""
say "--- memory smoke ---"
run_check "smoke-memory.sh" bash "$ROOT/scripts/smoke-memory.sh"

# Summary
if [[ "$JSON" -eq 1 ]]; then
  status=READY
  [[ "${#BLOCKERS[@]}" -gt 0 ]] && status=BLOCKED
  python3 - "$status" "$VERSION" ${BLOCKERS[@]+"${BLOCKERS[@]}"} <<'PY'
import json
import sys

status, version, *blockers = sys.argv[1:]
print(json.dumps({
    "schema": "repo_release_check.v1",
    "repo": "mq-agent",
    "status": status,
    "blockers": blockers,
    "warnings": [],
    "evidence": {"version": version},
}))
PY
  exit 0
fi

echo ""
if [[ "${#BLOCKERS[@]}" -eq 0 ]]; then
  echo "=== All checks passed — ready to release v${VERSION} ==="
  echo "Next: push a release-prep branch, open a PR, wait for CI, then tag from merged main."
else
  echo "=== ${#BLOCKERS[@]} check(s) failed — fix before releasing ===" >&2
  exit 1
fi
