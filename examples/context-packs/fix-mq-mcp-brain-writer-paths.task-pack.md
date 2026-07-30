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

## CodeGraph queries

Use the installed CodeGraph MCP tools directly. Treat returned source as already
read; fall back to targeted reads only for missing, stale, or unsupported detail.

* `codegraph_context` — map task "fix mq-mcp brain writer paths" in `mq-mcp` first

## Exclusions

* `irrelevant` — unrelated UMS docs
* `irrelevant` — old release notes
* `irrelevant` — full repo README files
* `irrelevant` — raw or unsanitized logs
