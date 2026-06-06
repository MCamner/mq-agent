#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ERRORS=0

fail() { echo "FAIL: $1" >&2; ERRORS=$((ERRORS + 1)); }
ok() { echo "OK:   $1"; }

echo "=== skill quality review ==="

for skill_doc in "$ROOT"/skills/*/SKILL.md; do
  [[ -f "$skill_doc" ]] || continue
  rel="${skill_doc#$ROOT/}"
  score=0

  if grep -q '^## When to use' "$skill_doc" && grep -q '^### Should trigger' "$skill_doc"; then
    score=$((score + 1))
  fi
  if grep -q '^## When not to use' "$skill_doc" && grep -Eq '^(Never:|## Boundary|## Workflow Rules)' "$skill_doc"; then
    score=$((score + 1))
  fi
  skill_name="$(basename "$(dirname "$skill_doc")")"
  if awk -v name="$skill_name" '
    $0 ~ "^### " {
      in_section = (tolower(substr($0, 5)) == name)
    }
    in_section && /^Outputs?:/ {
      found = 1
    }
    END { exit found ? 0 : 1 }
  ' "$ROOT/SKILLS.md"; then
    score=$((score + 1))
  fi
  if grep -Eq '^(Always inspect:|## Verification|Check for:)' "$skill_doc"; then
    score=$((score + 1))
  fi
  if grep -q '^### Should not trigger' "$skill_doc" && grep -q '→' "$skill_doc"; then
    score=$((score + 1))
  fi

  if [[ "$score" -ge 4 ]]; then
    ok "$rel quality score $score/5"
  else
    fail "$rel quality score $score/5 (need >=4)"
  fi
done

if [[ "$ERRORS" -eq 0 ]]; then
  echo "=== skill quality review passed ==="
else
  echo "=== $ERRORS skill quality issue(s) found ===" >&2
  exit 1
fi
