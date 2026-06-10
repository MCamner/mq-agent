# Stack Health History

Per-repo health score trends across multiple stack sweeps.

## Quick start

```bash
# Run a sweep (writes to history automatically)
mq-agent stack sweep

# Show last 5 sweeps
mq-agent stack history

# Show last 10 sweeps
mq-agent stack history --limit 10

# Diff the two most recent sweeps
mq-agent stack history --diff

# Machine-readable output
mq-agent stack history --json
```

## How it works

Every `mq-agent stack sweep` (without `--dry-run`) appends one snapshot to:

```text
~/.mq-agent/sweep-history.jsonl
```

Each line is a JSON record:

```json
{
  "ts": "2026-06-10T12:34:56.789012+00:00",
  "results": [
    {"name": "mq-agent", "overall": 100, "publish": 16, "skipped": false},
    {"name": "mq-mcp",   "overall":  95, "publish": 15, "skipped": false},
    {"name": "mq-hal",   "skipped": true}
  ]
}
```

## Example: history table

```text
               Stack health history — last 3 sweep(s)
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Repo             ┃ 2026-06-08  ┃ 2026-06-09  ┃ 2026-06-10  ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ mqlaunch         │ 100         │ 100         │ 100         │
│ mq-agent         │ 98          │ 100         │ 100         │
│ mq-mcp           │ 90          │ 92          │  95         │
│ repo-signal      │ 85          │ 85          │  88         │
│ mq-hal           │ skip        │ skip        │  72         │
│ mq-image-analyze │ 90          │ 90          │  90         │
│ mq-ums           │  —          │ 75          │  80         │
│ mqobsidian       │ skip        │ skip        │ skip        │
└──────────────────┴─────────────┴─────────────┴─────────────┘

History: ~/.mq-agent/sweep-history.jsonl  (3 sweep(s) total)
```

## Example: diff between two sweeps

```text
                 Sweep diff: 2026-06-09 12:00 → 2026-06-10 12:00
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Repo             ┃ 2026-06-09      ┃ 2026-06-10      ┃ Delta    ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ mqlaunch         │ 100             │ 100             │ ==       │
│ mq-agent         │ 100             │ 100             │ ==       │
│ mq-mcp           │  92             │  95             │ +3       │
│ repo-signal      │  85             │  88             │ +3       │
│ mq-hal           │  —              │  72             │ —        │
│ mq-image-analyze │  90             │  90             │ ==       │
│ mq-ums           │  75             │  80             │ +5       │
│ mqobsidian       │  —              │  —              │ —        │
└──────────────────┴─────────────────┴─────────────────┴──────────┘
```

## JSON scripting

```bash
# Latest sweep scores as JSON
mq-agent stack history --json --limit 1 | jq '.[0].results[] | {name, overall}'

# Repos below 80 in most recent sweep
mq-agent stack history --json --limit 1 \
  | jq '.[0].results[] | select(.skipped == false and .overall < 80) | .name'
```

## History file format

* One JSON object per line (JSONL)
* Appended by every non-dry-run `stack sweep`
* Never truncated automatically — use `--limit` when viewing
* Manually editable / deletable; a missing file is handled gracefully

## Companion commands

```bash
mq-agent stack sweep --dry-run    # preview (does NOT write to history)
mq-agent stack sweep              # sweep + append to history
mq-agent stack sweep --brain      # sweep + brain notes + history
mq-agent stack status             # live status without signal scoring
```
