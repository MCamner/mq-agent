# Operator Dashboard

`mq-agent dashboard` is the v1.19 operator snapshot for the mq stack.

It is read-only and combines:

| Area | Source |
| --- | --- |
| Stack health | `mq-agent stack cockpit` |
| Release readiness | Cockpit release gate summary |
| Contracts | Cockpit contract statuses |
| Brain freshness | Latest mqobsidian stack-truth note |
| Ollama | Active model profile and local model inventory |

## Commands

```bash
mq-agent dashboard          # rendered operator table
mq-agent dashboard --json   # machine-readable snapshot
mq-agent tui                # Textual dashboard with refreshable operator panels
```

The dashboard does not mutate repos, write brain notes or switch model profiles.
Use the reported `next_action` to choose the next command.

## TUI

`mq-agent tui` shows four operator panels above the command log:

| Panel | Shows |
| --- | --- |
| Stack | Release gate, contract status, repo count and dirty/action counts |
| Brain | Stack-truth freshness and note path |
| Ollama | Active model profile and local model count |
| Next | Overall state and the recommended next action |

Press `r` to refresh the panels without running a command.
