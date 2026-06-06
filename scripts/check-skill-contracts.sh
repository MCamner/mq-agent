#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ERRORS=0

fail() { echo "FAIL: $1" >&2; ERRORS=$((ERRORS + 1)); }
ok() { echo "OK:   $1"; }

echo "=== skill contract check ==="

SKILLS_FILE="$ROOT/SKILLS.md"
if [[ ! -f "$SKILLS_FILE" ]]; then
  fail "SKILLS.md missing"
else
  ok "SKILLS.md exists"
fi

while IFS= read -r rel; do
  [[ -z "$rel" ]] && continue
  if [[ -f "$ROOT/$rel" ]]; then
    ok "skill path exists: $rel"
  else
    fail "skill path missing: $rel"
  fi
done < <(grep -Eo 'skills/[^` ]+/SKILL\.md' "$SKILLS_FILE" | sort -u)

mapfile -t MISSING_OUTPUTS < <(awk '
  /^### / {
    if (section != "" && has_command && !has_outputs) {
      print section
    }
    section = substr($0, 5)
    has_command = 0
    has_outputs = 0
    next
  }
  /^## / {
    if (section != "" && has_command && !has_outputs) {
      print section
    }
    section = ""
    has_command = 0
    has_outputs = 0
    next
  }
  section != "" && /^Command:/ { has_command = 1 }
  section != "" && /^Outputs?:/ { has_outputs = 1 }
  END {
    if (section != "" && has_command && !has_outputs) {
      print section
    }
  }
' "$SKILLS_FILE")

for section in "${MISSING_OUTPUTS[@]}"; do
  fail "skill missing Outputs contract: $section"
done

while IFS= read -r skill_doc; do
  [[ -z "$skill_doc" ]] && continue
  rel="${skill_doc#$ROOT/}"
  if grep -q '^## When to use' "$skill_doc"; then
    ok "skill has trigger guidance: $rel"
  else
    fail "skill missing When to use: $rel"
  fi
  if grep -q '^## When not to use' "$skill_doc"; then
    ok "skill has near-miss guidance: $rel"
  else
    fail "skill missing When not to use: $rel"
  fi
done < <(find "$ROOT/skills" -mindepth 2 -maxdepth 2 -name 'SKILL.md' -type f | sort)

MATRIX="$ROOT/docs/CROSS_REPO_ROUTING_MATRIX.md"
if [[ ! -f "$MATRIX" ]]; then
  fail "docs/CROSS_REPO_ROUTING_MATRIX.md missing"
else
  ok "cross-repo routing matrix exists"
  for owner in mq-agent mq-mcp repo-signal mq-image-analyze macos-scripts mq-hal; do
    if grep -q "$owner" "$MATRIX"; then
      ok "routing matrix covers $owner"
    else
      fail "routing matrix missing $owner"
    fi
  done
fi

if [[ "$ERRORS" -eq 0 ]]; then
  echo "=== skill contract check passed ==="
else
  echo "=== $ERRORS skill contract check(s) failed ===" >&2
  exit 1
fi
