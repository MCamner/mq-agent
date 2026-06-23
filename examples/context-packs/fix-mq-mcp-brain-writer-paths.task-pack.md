---
schema: context-pack.v1
target: both
task: fix mq-mcp brain writer paths
generated_at: 2026-06-21T17:25:14+00:00
repo: mq-mcp
summary: Minimum context needed for: fix mq-mcp brain writer paths
---

# Task Context Pack

## Relevant repos

* mq-mcp

## Relevant files

* mq-mcp/.mq/context/repo-card.md
* mqobsidian/memory/context-cards/mq-mcp-card.md

## Relevant decisions

* Durable memory lives in mqobsidian; runtime truth stays in the source repo.

## Notes

* Prefer the mqobsidian cards above before broad repo scans.
* `.codegraph/` is present in `mq-mcp`; ask CodeGraph for callers/impact before broad grep.
* Use CodeGraph for source structure only; use mqobsidian cards/packs for durable memory and repo boundaries.

## Exclusions

* `irrelevant` — unrelated UMS docs
* `irrelevant` — old release notes
* `irrelevant` — full repo README files
* `irrelevant` — raw or unsanitized logs
