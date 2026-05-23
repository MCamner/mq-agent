# Demo

End-to-end walkthrough of `mq-agent` on a real repo.

## Setup

```bash
uv pip install -e ".[dev,signal]"
export OPENAI_API_KEY="sk-proj-..."
cd ~/mq-agent
```

## Step 1 — Environment check

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
│ mq-mcp (optional) │ ✗ FAIL │ Start mq-mcp on :8765 │
└───────────────────┴────────┴───────────────────────┘
All required checks passed.
```

## Step 2 — Score (no API key needed)

```bash
mq-agent score .
```

```text
╭──────────────────────────────── README Score ────────────────────────────────╮
│ README score: 100/100  [██████████]                                          │
│                                                                              │
│ Present:                                                                     │
│   ✓ title                                                                    │
│   ✓ short_pitch                                                              │
│   ✓ install                                                                  │
│   ✓ usage                                                                    │
│   ✓ examples                                                                 │
│   ✓ screenshots_demo                                                         │
│   ✓ badges                                                                   │
│   ✓ license                                                                  │
│   ✓ roadmap                                                                  │
│   ✓ contributing                                                             │
│                                                                              │
│ Missing:                                                                     │
│   (none — perfect score!)                                                    │
╰──────────────────────────────────────────────────────────────────────────────╯
╭───────────────────────────── Publish Checklist ──────────────────────────────╮
│ Publish checklist: 16/16  [PASS]                                             │
│                                                                              │
│ [Front door]                                                                 │
│   ✓ README exists                                                            │
│   ✓ README has quick start                                                   │
│   ✓ README links to GitHub Pages                                             │
│   ✓ README mentions demo                                                     │
│   ✓ README mentions screenshots or gallery                                   │
│                                                                              │
│ [Public quality]                                                             │
│   ✓ LICENSE exists      ✓ CHANGELOG exists   ✓ VERSION exists               │
│   ✓ .gitignore exists   ✓ README mentions roadmap                            │
│   ✓ issue templates exist                                                    │
│                                                                              │
│ [GitHub Pages]                                                               │
│   ✓ docs folder exists                                                       │
│   ✓ GitHub Pages landing exists                                              │
│   ✓ docs screenshots folder exists                                           │
│                                                                              │
│ Next: Repo looks publish-ready from the static checklist.                    │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## Step 3 — Full signal assessment

```bash
mq-agent signal .
```

```text
╭─────────────────────────── mq-agent · Python project ───────────────────────╮
│ Overall:  100/100                                                            │
│ README:   100/100                                                            │
│ Publish:  16/16  [PASS]                                                      │
╰──────────────────────────────────────────────────────────────────────────────╯

Focus areas:
  1. Foundation looks healthy; improve analysis depth next

                            AI Improvement Plan
┏━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ # ┃ Step                                 ┃ Status     ┃ Note                ┃
┡━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│ 1 │ Scan the repository                  │ success    │ 60 files, main      │
│ 2 │ Analyze the repository               │ success    │ Python project      │
│ 3 │ Read the README file                 │ success    │ 100/100 score       │
│ 4 │ Check the git log                    │ success    │ Clean working tree  │
│ 5 │ Review repository status             │ success    │ Clean working tree  │
└───┴──────────────────────────────────────┴────────────┴─────────────────────┘

✓ Repo looks healthy
Next: Repo looks publish-ready from the static checklist.
```

## Step 4 — Audit (dry-run)

```bash
mq-agent audit . --dry-run
```

Shows the full AI-generated audit plan without executing any steps. Safe to run on any repo.

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
