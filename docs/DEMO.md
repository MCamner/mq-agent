# Demo

End-to-end walkthrough of `mq-agent` on a real repo.

## Setup

```bash
uv pip install -e ".[dev,signal]"
export OPENAI_API_KEY="sk-..."
cd ~/your-repo
```

## Step 1 — Environment check

```bash
mq-agent doctor
```

```
┌───────────────────┬────────┬───────────────────────┐
│ Check             │ Status │ Action                │
├───────────────────┼────────┼───────────────────────┤
│ OPENAI_API_KEY    │ ✓ OK   │                       │
│ git               │ ✓ OK   │                       │
│ uv                │ ✓ OK   │                       │
│ Python ≥ 3.11     │ ✓ OK   │                       │
│ repo-signal       │ ✓ OK   │                       │
│ mq-mcp (optional) │ ✗ FAIL │ Start mq-mcp on :8765 │
└───────────────────┴────────┴───────────────────────┘
All required checks passed.
```

## Step 2 — Score (no API key needed)

```bash
mq-agent score .
```

```
╭─── README Score ───────────────────────╮
│ README score: 100/100  [██████████]    │
│ ✓ title  ✓ install  ✓ usage            │
│ ✓ badges  ✓ license  ✓ roadmap         │
╰────────────────────────────────────────╯
╭─── Publish Checklist ──────────────────╮
│ Publish checklist: 16/16  [PASS]       │
│ Repo looks publish-ready.              │
╰────────────────────────────────────────╯
```

## Step 3 — Full signal assessment

```bash
mq-agent signal .
```

```
╭─── mq-agent · Python project ─────────╮
│ Overall:  100/100                      │
│ README:   100/100                      │
│ Publish:  16/16  [PASS]                │
╰────────────────────────────────────────╯

Focus areas:
  1. Foundation looks healthy; improve analysis depth next

AI Improvement Plan
┌───┬──────────────────────┬─────────┬─────────────────────┐
│ # │ Step                 │ Status  │ Note                │
├───┼──────────────────────┼─────────┼─────────────────────┤
│ 1 │ Scan repository      │ success │ 60 files, main      │
│ 2 │ Analyze repo         │ success │ Python project      │
│ 3 │ Read README          │ success │ 100/100 score       │
│ 4 │ Check git log        │ success │ Clean working tree  │
└───┴──────────────────────┴─────────┴─────────────────────┘
✓ Repo looks healthy
```

## Step 4 — Audit (dry-run)

```bash
mq-agent audit . --dry-run
```

Shows the full AI-generated audit plan without executing any steps.

## Step 5 — Release check

```bash
mq-agent release-check --dry-run
```

Validates: git state, version alignment, changelog, test coverage, CI status.

## JSON output

Every command supports `--json` for scripting:

```bash
mq-agent audit . --json | jq '.steps[] | select(.status == "failed")'
mq-agent score . --json | jq '.readme_score'
```

## TUI

```bash
mq-agent tui
```

Launches the Textual dashboard with sidebar navigation and live log output.
