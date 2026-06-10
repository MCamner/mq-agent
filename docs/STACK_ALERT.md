# Stack Alert

Threshold-based health alerting across the MQ stack.

## Quick start

```bash
# Standalone — compare last two sweeps
mq-agent stack alert

# Custom thresholds
mq-agent stack alert --threshold 5 --min-score 90

# Machine-readable (exits 1 when alerts found)
mq-agent stack alert --json

# Inline after a sweep
mq-agent stack sweep --alert
mq-agent stack sweep --alert --threshold 5
```

## Alert conditions

A repo triggers an alert when **either** condition is true:

| Condition | Default | Flag |
| --- | --- | --- |
| Score dropped ≥ N points since last sweep | 10 | `--threshold N` |
| Current score below min-score | 80 | `--min-score N` |

Both conditions are evaluated per-repo. A repo can carry both reasons at once.
Skipped repos are never alerted.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | No alerts — all repos healthy or stable |
| 1 | One or more alerts found |

Exit code 1 makes `stack alert` CI-friendly: pipe it into a GitHub Actions step
or a pre-push hook to gate on regressions.

## Example output

```text
Stack alerts  2026-06-09 12:00 → 2026-06-10 12:00
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Repo             ┃ Prev  ┃ Now ┃ Delta  ┃ Reason                             ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ mq-mcp           │ 95    │ 70  │ -25    │ dropped 25 pts, below 80           │
│ repo-signal      │ 88    │ 77  │ -11    │ dropped 11 pts, below 80           │
└──────────────────┴───────┴─────┴────────┴────────────────────────────────────┘
```

No alerts:

```text
✓ No alerts — all repos healthy or stable.
Compared: 2026-06-09 12:00 → 2026-06-10 12:00
```

## JSON output

```bash
mq-agent stack alert --json
```

```json
[
  {
    "name": "mq-mcp",
    "prev": 95,
    "current": 70,
    "delta": -25,
    "reasons": ["dropped 25 pts", "below 80"]
  }
]
```

Empty array `[]` + exit 0 when no alerts.

## CI integration

```yaml
# .github/workflows/stack-health.yml
- name: Stack alert
  run: mq-agent stack alert --json
  # Fails the job if any repo regressed
```

```bash
# pre-push hook
mq-agent stack alert || { echo "Stack regression — fix before push"; exit 1; }
```

## Inline with sweep

`--alert` runs the alert check automatically at the end of a sweep:

```bash
mq-agent stack sweep --alert
mq-agent stack sweep --alert --threshold 5
```

The sweep still writes to history and prints the summary table before evaluating alerts.

## Companion commands

```bash
mq-agent stack sweep            # sweep and save history
mq-agent stack history          # trend table
mq-agent stack history --diff   # delta between last two sweeps
mq-agent stack alert            # alert check (standalone)
```
