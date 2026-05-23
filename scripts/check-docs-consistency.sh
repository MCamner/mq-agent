#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(cat "$ROOT/VERSION")"
ERRORS=0

fail() { echo "FAIL: $1" >&2; ERRORS=$((ERRORS + 1)); }
ok()   { echo "OK:   $1"; }

echo "=== docs consistency check v${VERSION} ==="

# pyproject.toml version
TOML_VER="$(grep '^version' "$ROOT/pyproject.toml" | head -1 | sed 's/.*"\(.*\)".*/\1/')"
if [[ "$TOML_VER" == "$VERSION" ]]; then
  ok "pyproject.toml version matches VERSION ($VERSION)"
else
  fail "pyproject.toml version '$TOML_VER' != VERSION '$VERSION'"
fi

# README badge
if grep -q "status-v${VERSION}" "$ROOT/README.md"; then
  ok "README.md contains status-v${VERSION} badge"
else
  fail "README.md missing status-v${VERSION} badge"
fi

# README status section
if grep -q "## v${VERSION} status" "$ROOT/README.md"; then
  ok "README.md has ## v${VERSION} status section"
else
  fail "README.md missing ## v${VERSION} status section"
fi

# CHANGELOG
if grep -q "\[v${VERSION}\]" "$ROOT/CHANGELOG.md"; then
  ok "CHANGELOG.md contains [v${VERSION}]"
else
  fail "CHANGELOG.md missing [v${VERSION}] entry"
fi

# Pages
if grep -q "v${VERSION}" "$ROOT/docs/index.html"; then
  ok "docs/index.html contains v${VERSION}"
else
  fail "docs/index.html missing v${VERSION}"
fi

# Source readability guards
for spec in \
  "README.md:200" \
  "CHANGELOG.md:150" \
  "pyproject.toml:40" \
  "docs/COMMAND_SURFACE.md:80" \
  "docs/SEMANTIC_MEMORY.md:40" \
  "scripts/smoke-mqlaunch.sh:35" \
  "scripts/smoke-memory.sh:20" \
  "release-check.sh:55" \
  ".github/workflows/tests.yml:20" \
  ".github/workflows/install-smoke.yml:20"; do
  file="${spec%%:*}"
  min_lines="${spec##*:}"
  line_count="$(wc -l < "$ROOT/$file" | tr -d ' ')"
  if [[ "$line_count" -ge "$min_lines" ]]; then
    ok "$file has readable line structure ($line_count lines)"
  else
    fail "$file appears flattened ($line_count lines, expected at least $min_lines)"
  fi
done

# Stale score guards — check README only (docs/ may contain historical references in ROADMAP/CHANGELOG)
for stale in "70/100" "8/16" "v0.2.1" "v0.2.0 status"; do
  if grep -q "$stale" "$ROOT/README.md" 2>/dev/null; then
    fail "Stale string found in README.md: '$stale'"
  else
    ok "README.md clean of: '$stale'"
  fi
done

for stale in \
  "Planned for v0.4.0" \
  "planned for v0.3.0" \
  "Planned for v0.2.0" \
  "mq-agent currently runs standalone"; do
  if grep -R -n "$stale" "$ROOT/docs" "$ROOT/README.md" >/dev/null 2>&1; then
    fail "Stale integration wording found: '$stale'"
  else
    ok "integration docs clean of: '$stale'"
  fi
done

# Also check docs/index.html specifically (not ROADMAP/DEMO which may reference old versions)
for stale in "70/100" "8/16"; do
  if grep -q "$stale" "$ROOT/docs/index.html" 2>/dev/null; then
    fail "Stale string found in docs/index.html: '$stale'"
  else
    ok "docs/index.html clean of: '$stale'"
  fi
done

# mqlaunch command-count consistency
MQ_DOCS=(
  "$ROOT/README.md"
  "$ROOT/CHANGELOG.md"
  "$ROOT/docs/COMMAND_SURFACE.md"
  "$ROOT/docs/ROADMAP.md"
  "$ROOT/docs/MQLAUNCH_INTEGRATION.md"
  "$ROOT/docs/MQ_ECOSYSTEM.md"
)

for stale in \
  "3 prompt commands" \
  "3 direct prompt commands" \
  "5 prompt commands" \
  "5 direct prompt commands" \
  "all 8 mqlaunch-callable"; do
  if grep -R -n "$stale" "${MQ_DOCS[@]}" >/dev/null 2>&1; then
    fail "Stale mqlaunch command-count wording found: '$stale'"
  else
    ok "mqlaunch docs clean of: '$stale'"
  fi
done

if grep -q "12-item agent menu + 6 direct prompt commands" "$ROOT/README.md"; then
  ok "README.md has canonical mqlaunch count"
else
  fail "README.md missing canonical mqlaunch count"
fi

if grep -q "12-item agent menu + 6 prompt commands" "$ROOT/docs/MQ_ECOSYSTEM.md"; then
  ok "MQ_ECOSYSTEM.md has canonical mqlaunch count"
else
  fail "MQ_ECOSYSTEM.md missing canonical mqlaunch count"
fi

if [[ -f "$ROOT/docs/COMMAND_SURFACE.md" ]]; then
  ok "docs/COMMAND_SURFACE.md exists"
else
  fail "docs/COMMAND_SURFACE.md missing"
fi

for required in \
  "The mqlaunch agent menu has exactly 12 items." \
  "exposes 6 direct subcommands plus the menu entrypoint." \
  "exposes exactly 6 direct prompt commands." \
  "scripts/smoke-mqlaunch.sh"; do
  if grep -q "$required" "$ROOT/docs/COMMAND_SURFACE.md"; then
    ok "COMMAND_SURFACE.md contains: $required"
  else
    fail "COMMAND_SURFACE.md missing: $required"
  fi
done

for cmd in "agent score" "agent audit" "agent doctor" "agent release-check" "agent mcp-status" "agent mcp-tools"; do
  if grep -q "$cmd" "$ROOT/README.md" && \
     grep -q "$cmd" "$ROOT/docs/MQLAUNCH_INTEGRATION.md" && \
     grep -q "$cmd" "$ROOT/docs/COMMAND_SURFACE.md"; then
    ok "mqlaunch direct command documented: $cmd"
  else
    fail "mqlaunch direct command missing from README, MQLAUNCH_INTEGRATION or COMMAND_SURFACE: $cmd"
  fi
done

echo ""
if [[ "$ERRORS" -eq 0 ]]; then
  echo "=== All consistency checks passed ==="
else
  echo "=== $ERRORS check(s) failed ===" >&2
  exit 1
fi
