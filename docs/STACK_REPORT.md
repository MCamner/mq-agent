# Stack Report & Release Check

Two commands that give a consolidated view of the whole MQ stack.

## Stack report

```bash
mq-agent stack report          # score, trend, alert, ready — per repo
mq-agent stack report --json   # machine-readable
```

Reads sweep history — no API key, no network calls.

### Columns

| Column | Source | Meaning |
| --- | --- | --- |
| Score | Latest sweep | repo-signal overall/100 |
| Trend | Last two sweeps | ↑+N improved, ↓N dropped, == stable |
| Alert | `_compute_alerts` | ⚠ if dropped ≥ 10 pts or below 80 |
| Ready | Score + alert | ✓ if score ≥ 80 and no alert |

### Example

```text
                    mq-stack Report  2026-06-10 12:00
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┓
┃ Repo               ┃ Score     ┃ Trend    ┃ Alert   ┃ Ready   ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━┩
│ mqlaunch           │ 100/100   │ ==       │ ✓       │ ✓       │
│ mq-agent           │ 100/100   │ ↑+2      │ ✓       │ ✓       │
│ mq-mcp             │  95/100   │ ↑+3      │ ✓       │ ✓       │
│ repo-signal        │  88/100   │ ==       │ ✓       │ ✓       │
│ mq-hal             │  72/100   │ ↓-5      │ ⚠       │ ~       │
│ mq-image-analyze   │  90/100   │ ==       │ ✓       │ ✓       │
│ mq-ums             │  80/100   │ new      │ ✓       │ ✓       │
│ mqobsidian         │ —         │ —        │ —       │ —       │
└────────────────────┴───────────┴──────────┴─────────┴─────────┘

6/7 repos ready (score ≥ 80, no alert)
```

`stack report` always exits 0 — it is informational only. Use `stack alert` for gating.

---

## Stack release-check

```bash
mq-agent stack release-check            # per-repo release gate
mq-agent stack release-check --dry-run  # list repos without checking
mq-agent stack release-check --json     # machine-readable, exits 1 on NO-GO
```

Runs local checks per repo — no API key, no network calls.

### Checks per repo

| Check | Blocker | Trigger |
| --- | --- | --- |
| VERSION file exists | yes | missing `VERSION` |
| README.md exists | yes | missing `README.md` |
| CHANGELOG entry for version | warning | missing entry |
| Clean working tree | warning | uncommitted changes |
| Unpushed commits | warning | commits ahead of remote |
| ROADMAP.md exists | warning | missing `ROADMAP.md` |

Blockers prevent GO. Warnings are shown but do not block.

`mqobsidian` is excluded (no VERSION/CHANGELOG contract).

### Example

```text
                          mq-stack Release Check
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ Repo               ┃ Version   ┃ Branch     ┃ Blockers     ┃ Warnings            ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│ mqlaunch           │ 1.0.0     │ main       │ none         │ none                │
│ mq-agent           │ 1.9.0     │ main       │ none         │ none                │
│ mq-mcp             │ 1.10.1    │ main       │ none         │ none                │
│ repo-signal        │ 1.4.0     │ main       │ none         │ none                │
│ mq-hal             │ 1.2.0     │ mq/docs    │ none         │ not on main         │
│ mq-image-analyze   │ 1.4.0     │ mq/files   │ none         │ not on main         │
│ mq-ums             │ 0.1.4     │ main       │ none         │ CHANGELOG missing   │
└────────────────────┴───────────┴────────────┴──────────────┴─────────────────────┘

✓ All repos clear — stack is GO.
```

Exit 0 when all repos have no blockers, exit 1 otherwise.

### JSON output

```bash
mq-agent stack release-check --json | jq '.repos[] | select(.go == false) | {name, blockers}'
```

---

## Typical workflow

```bash
mq-agent stack sweep              # update health scores
mq-agent stack report             # consolidated view
mq-agent stack alert              # regression check (exit 1 on drop)
mq-agent stack release-check      # release gate (exit 1 on blocker)
```
