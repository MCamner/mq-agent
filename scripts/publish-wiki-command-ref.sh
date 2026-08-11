#!/usr/bin/env bash
#
# Publish the generated command reference to the GitHub Wiki.
#
# Contract:
#   - The repo is authoritative. This script only projects an already-generated
#     file; it never generates into the wiki clone.
#   - Idempotent and diff-driven: pushes only when the content actually changed.
#   - Warn-only: a publishing failure must never invalidate a release, so every
#     failure path exits 0.
#   - Touches exactly one page. The hand-written wiki pages are out of scope.
#
# Usage:
#   bash scripts/publish-wiki-command-ref.sh [--dry-run]

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$REPO_ROOT/docs/generated/Command-Reference.md"
# Overridable so the publish flow can be exercised against a local bare repo.
WIKI_URL="${MQ_WIKI_URL:-git@github.com:MCamner/mq-agent.wiki.git}"
PAGE="Command-Reference.md"

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

warn() { printf '[wiki] %s\n' "$1"; }

if [[ ! -f "$SOURCE" ]]; then
  warn "generated reference not found: $SOURCE"
  warn "run 'python tools/generate_command_reference.py' first — skipping"
  exit 0
fi

# Refuse to publish a stale page: the repo must be the source of truth.
if ! python3 "$REPO_ROOT/tools/generate_command_reference.py" --check >/dev/null 2>&1; then
  warn "generated reference is stale relative to the code — skipping"
  warn "run 'python tools/generate_command_reference.py' and commit"
  exit 0
fi

WIKI_TMP="$(mktemp -d)"
trap 'rm -rf "$WIKI_TMP"' EXIT

if ! git clone --quiet --depth 1 "$WIKI_URL" "$WIKI_TMP" 2>/dev/null; then
  warn "could not clone the wiki remote — skipping"
  exit 0
fi

if [[ -f "$WIKI_TMP/$PAGE" ]] && cmp -s "$SOURCE" "$WIKI_TMP/$PAGE"; then
  warn "$PAGE unchanged — nothing to push"
  exit 0
fi

cp "$SOURCE" "$WIKI_TMP/$PAGE"

if [[ "$DRY_RUN" -eq 1 ]]; then
  warn "dry run — would push an updated $PAGE"
  git -C "$WIKI_TMP" --no-pager diff --stat -- "$PAGE" || true
  exit 0
fi

if ! git -C "$WIKI_TMP" add "$PAGE" 2>/dev/null; then
  warn "could not stage $PAGE — skipping"
  exit 0
fi

if git -C "$WIKI_TMP" diff --cached --quiet; then
  warn "$PAGE unchanged after staging — nothing to push"
  exit 0
fi

if ! git -C "$WIKI_TMP" commit --quiet -m "docs: regenerate $PAGE from the Typer app" 2>/dev/null; then
  warn "could not commit $PAGE — skipping"
  exit 0
fi

if ! git -C "$WIKI_TMP" push --quiet 2>/dev/null; then
  warn "could not push to the wiki remote — skipping"
  exit 0
fi

warn "$PAGE published"
exit 0
