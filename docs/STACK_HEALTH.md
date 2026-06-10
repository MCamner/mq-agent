# Stack Health

Multi-repo health sweep across all core MQ repos.

## Quick start

```bash
# Dry-run — shows which repos would be scanned
mq-agent stack sweep --dry-run

# Full sweep — signal + brain notes per repo
mq-agent stack sweep --brain

# Full sweep + consolidated brain ADR
mq-agent stack sweep --brain --decide

# Via mqlaunch
mqlaunch agent    # → choose 18. Stack health sweep
```

## What it does

`mq-agent stack sweep` runs repo-signal on every repo in `MQ_STACK_REPOS` in sequence:

```text
For each repo in mq-stack:
  1. mq-agent signal <path>          ← repo-signal scan
  2. → brain note (with --brain)     ← writes reviews/repo-signal:<name>.md
  3. Summary table printed

With --decide:
  4. mq-agent decide "MQ Stack Health Snapshot"  ← brain ADR
```

## Core repos scanned

| Repo | Path | Role |
| --- | --- | --- |
| mqlaunch | ~/macos-scripts | Terminal entrypoint |
| mq-agent | ~/mq-agent | Orchestrator |
| mq-mcp | ~/mq-mcp | Runtime/review truth |
| repo-signal | ~/repo-signal | Repo intelligence |
| mq-hal | ~/mq-hal | Local reasoning shell |
| mq-image-analyze | ~/mq-image-analyze | Visual perception |
| mq-ums | ~/mq-ums | UMS/IGEL tooling |
| mqobsidian | ~/mqobsidian | Second brain |

Repos whose path does not exist are skipped and noted in output.

## Example output

```text
─────────────── mq-agent ──────────────
╭──────────────────── mq-agent · Python project ─────────────────────╮
│ Overall:  100/100   README: 100/100   Publish: 16/16               │
╰─────────────────────────────────────────────────────────────────────╯
→ brain: reviews/repo-signal:mq-agent.md

─────────────── mq-mcp ───────────────
╭──────────────────── mq-mcp · Python project ───────────────────────╮
│ Overall:  95/100   README: 95/100   Publish: 15/16                 │
╰─────────────────────────────────────────────────────────────────────╯
→ brain: reviews/repo-signal:mq-mcp.md

...

┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┓
┃ Repo             ┃ Overall    ┃ Publish ┃ Status ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━┩
│ mqlaunch         │ 100/100    │ 16      │ ✓      │
│ mq-agent         │ 100/100    │ 16      │ ✓      │
│ mq-mcp           │  95/100    │ 15      │ ~      │
│ repo-signal      │  88/100    │ 14      │ ~      │
│ mq-hal           │  —         │ —       │ skipped│
│ mq-image-analyze │  90/100    │ 14      │ ~      │
│ mq-ums           │  —         │ —       │ skipped│
│ mqobsidian       │  —         │ —       │ skipped│
└──────────────────┴────────────┴─────────┴────────┘

→ brain ADR: decisions/mq-stack-health-snapshot.md
```

## JSON output

```bash
mq-agent stack sweep --brain --json | jq '.[] | select(.skipped == false) | {name, overall}'
```

## Companion commands

```bash
mq-agent stack status          # version, branch, drift per repo (no signal)
mq-agent stack export          # write status table to mqobsidian
mq-agent swarm release-check   # cross-repo release gate via swarm
```

## Safety

* `stack sweep` is read-only without `--brain` / `--decide`
* `--brain` writes brain notes per repo (Class C, routed via `_brain_record_review`)
* `--decide` writes one ADR via `brain_record_decision` (Class C)
* All writes require mq-mcp to be running on `:8765`
