# Demo

End-to-end walkthrough of the MQ stack on a real repo.

## Setup

```bash
uv pip install -e ".[dev,signal]"
export OPENAI_API_KEY="sk-proj-..."
cd ~/mq-agent
```

## v1.5.0 — Full stack demo flow

Runs three commands in sequence: repo-signal readiness, mq-mcp review, and release gate.
Every step writes findings to the mqobsidian second brain.

### One-liner (via mqlaunch)

```bash
mqlaunch agent    # → choose 17. Demo flow (full stack)
```

### Manual run

```bash
# Step 1: repo-signal readiness → brain
mq-agent signal . --brain

# Step 2: review repo via mq-mcp → brain
mq-agent review repo . --brain

# Step 3: release-check (contract gate, dry-run safe)
mq-agent release-check --dry-run
```

### Or via the demo-flow script directly

```bash
~/macos-scripts/mqlaunch/commands/demo-flow.sh .
```

---

## Step-by-step output

### Step 1 — repo-signal readiness

```bash
mq-agent signal . --brain
```

```text
╭──────────────────────── mq-agent · Python project ────────────────────────╮
│ Overall:  100/100                                                           │
│ README:   100/100                                                           │
│ Publish:  16/16  [PASS]                                                     │
╰─────────────────────────────────────────────────────────────────────────────╯

Focus areas:
  1. Foundation looks healthy; improve analysis depth next

✓ Repo looks healthy
→ brain: reviews/repo-signal:mq-agent.md
```

### Step 2 — review repo → brain

```bash
mq-agent review repo . --brain
```

```text
╭─────────────────────── Review: repo ──────────────────────────╮
│ Findings: 2   HIGH: 0   MEDIUM: 1   LOW: 1   INFO: 0          │
│ Approved: yes                                                   │
╰─────────────────────────────────────────────────────────────────╯
→ brain: reviews/mq-agent.md
```

### Step 3 — release-check (contract gate)

```bash
mq-agent release-check --dry-run
```

```text
╭────────────────────── Release Check ─────────────────────────╮
│ git state    ✓ clean                                          │
│ version      ✓ VERSION matches pyproject.toml (1.5.0)        │
│ changelog    ✓ [v1.5.0] entry present                        │
│ tests        ✓ all passing                                    │
│ CI           ✓ last run green                                 │
╰───────────────────────────────────────────────────────────────╯
Ready to release.
```

---

## Environment check

```bash
mq-agent doctor
```

```text
                   mq-agent Doctor
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Check             ┃ Status ┃ Action                ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━┩
│ OPENAI_API_KEY    │ ✓ OK   │                       │
│ git               │ ✓ OK   │                       │
│ uv                │ ✓ OK   │                       │
│ Python ≥ 3.11     │ ✓ OK   │                       │
│ repo-signal       │ ✓ OK   │                       │
│ mq-mcp (optional) │ ✓ OK   │                       │
└───────────────────┴────────┴───────────────────────┘
All required checks passed.
```

## JSON output

Every command supports `--json` for scripting:

```bash
mq-agent signal . --json | jq '.scores'
mq-agent review repo . --json | jq '.findings[] | select(.severity == "HIGH")'
mq-agent release-check --json | jq '.ready'
```

## TUI

```bash
mq-agent tui
```

Launches the Textual dashboard with sidebar navigation and live log output.
