# Command Reference

Auto-generated from the live Typer application by
`tools/generate_command_reference.py`. Do not edit by hand — run the
generator and commit the result.

The repository is the authoritative source for the command surface.
This page is a projection of it.

## Overview

| Command | Type | Description |
|---|---|---|
| [`mq-agent agent-views`](#mq-agent-agent-views) | group | Build compressed agent-view read cards in the mqobsidian vault. |
| [`mq-agent audit`](#mq-agent-audit) | command | Audit a repository (read-only). |
| [`mq-agent b2`](#mq-agent-b2) | group | B2 prompt OS — route topics to prompts and run workflows. |
| [`mq-agent brain`](#mq-agent-brain) | group | Second brain vault commands (mqobsidian). |
| [`mq-agent browser`](#mq-agent-browser) | group | Browser-safe URL inspection and release verification. |
| [`mq-agent context`](#mq-agent-context) | group | Export compact repo-local .mq/context snapshots. |
| [`mq-agent dashboard`](#mq-agent-dashboard) | command | Show the v1.19 operator dashboard snapshot. |
| [`mq-agent decide`](#mq-agent-decide) | command | Record an architecture decision to mqobsidian/decisions/. Class C write. |
| [`mq-agent docs-audit`](#mq-agent-docs-audit) | command | Audit repository documentation: README, CHANGELOG, docstrings, /docs. |
| [`mq-agent doctor`](#mq-agent-doctor) | command | Check mq-agent environment and dependencies. |
| [`mq-agent fix-ci`](#mq-agent-fix-ci) | command | Diagnose CI failures and suggest fixes. |
| [`mq-agent learn`](#mq-agent-learn) | group | Learn commands — extraction, storage and promotion of review patterns. |
| [`mq-agent mcp`](#mq-agent-mcp) | group | Inspect and manage the local mq-mcp tool server. |
| [`mq-agent memory`](#mq-agent-memory) | group | Semantic repository memory commands. |
| [`mq-agent models`](#mq-agent-models) | group | Ollama model runtime commands. |
| [`mq-agent obsidian`](#mq-agent-obsidian) | group | Read and action the mqobsidian promotion inbox. |
| [`mq-agent plan`](#mq-agent-plan) | command | Create a plan for a goal using the AI planner. |
| [`mq-agent release-check`](#mq-agent-release-check) | command | Validate the repo is ready for a release. |
| [`mq-agent release-plan`](#mq-agent-release-plan) | command | Show the standard release plan. |
| [`mq-agent repo-summary`](#mq-agent-repo-summary) | command | Print a concise repo summary. |
| [`mq-agent review`](#mq-agent-review) | group | Pass-through mq-mcp review orchestration. |
| [`mq-agent route`](#mq-agent-route) | group | Inspect advisory local-first model routing. |
| [`mq-agent run`](#mq-agent-run) | command | Run a shell command safely, or the canonical stack runtime with --stack. |
| [`mq-agent run-tool`](#mq-agent-run-tool) | command | Run a specific MCP tool through mq-agent safety gates. |
| [`mq-agent score`](#mq-agent-score) | command | Quick README score (0–100) and publish checklist — no AI, instant result. Requires repo-signal to be installed: uv pip install repo-signal |
| [`mq-agent ship`](#mq-agent-ship) | group | Inspect release state, proof, and audit evidence (read-only). |
| [`mq-agent signal`](#mq-agent-signal) | command | Run a full repo-signal assessment: scan + README score + publish checklist + AI plan. Requires repo-signal to be installed: uv pip install repo-signal |
| [`mq-agent stack`](#mq-agent-stack) | group | mq-stack repo inventory, status, and Obsidian export. |
| [`mq-agent swarm`](#mq-agent-swarm) | group | Multi-agent swarm workflows. |
| [`mq-agent task`](#mq-agent-task) | group | Run declarative YAML task workflows. |
| [`mq-agent tools`](#mq-agent-tools) | command | List registered tools. Use --describe `<name>` for details, --mcp to include MCP tools. |
| [`mq-agent tui`](#mq-agent-tui) | command | Launch the Textual TUI dashboard. |
| [`mq-agent workflow`](#mq-agent-workflow) | group | Bounded multi-step workflow templates (list/show/plan). Read-only in v1. |

## `mq-agent agent-views`

Build compressed agent-view read cards in the mqobsidian vault.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent agent-views check`](#mq-agent-agent-views-check) | Report agent views that are stale vs their hot.md/index.md source. Drift guard: rebuilds in dry-run and flags any view that would be written or updated. Writes nothing; exits non-zero if any view is stale or errored (CI-friendly). This is what makes the per-system trigger trustworthy — and the precondition for ever defaulting the rebuild on. See docs/AGENT_VIEW_CONTRACT.md. |
| [`mq-agent agent-views rebuild`](#mq-agent-agent-views-rebuild) | Rebuild compressed agent views from each system's hot.md + index.md. Writes ``memory/learn/agent/`<system>`.md`` (read-order step 0). Pure extraction — never edits the curated hot.md/index.md source, and only writes inside the agent-views directory. Skips systems with no hot.md/index.md. With ``--system`` rebuilds only that one system (the surgical trigger a hot/index refresh runs after editing a single system). See docs/AGENT_VIEW_CONTRACT.md. |

## `mq-agent agent-views check`

Report agent views that are stale vs their hot.md/index.md source. Drift guard: rebuilds in dry-run and flags any view that would be written or updated. Writes nothing; exits non-zero if any view is stale or errored (CI-friendly). This is what makes the per-system trigger trustworthy — and the precondition for ever defaulting the rebuild on. See docs/AGENT_VIEW_CONTRACT.md.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--vault` | No | `""` | mqobsidian vault path (default: $MQ_OBSIDIAN_DIR or ~/mqobsidian) |
| `--system` | No | `""` | Check only this system's view (default: all) |
| `--json` | No | `false` | — |

## `mq-agent agent-views rebuild`

Rebuild compressed agent views from each system's hot.md + index.md. Writes ``memory/learn/agent/`<system>`.md`` (read-order step 0). Pure extraction — never edits the curated hot.md/index.md source, and only writes inside the agent-views directory. Skips systems with no hot.md/index.md. With ``--system`` rebuilds only that one system (the surgical trigger a hot/index refresh runs after editing a single system). See docs/AGENT_VIEW_CONTRACT.md.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--vault` | No | `""` | mqobsidian vault path (default: $MQ_OBSIDIAN_DIR or ~/mqobsidian) |
| `--system` | No | `""` | Rebuild only this system's view (default: all) |
| `--dry-run` | No | `false` | Show what would change without writing |
| `--json` | No | `false` | — |

## `mq-agent audit`

Audit a repository (read-only).

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | No | `.` | Repo path |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--dry-run` | No | `false` | Plan only, no execution |
| `--json` | No | `false` | JSON output |

## `mq-agent b2`

B2 prompt OS — route topics to prompts and run workflows.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent b2 history`](#mq-agent-b2-history) | Show recent b2tui workflow run history. |
| [`mq-agent b2 list`](#mq-agent-b2-list) | List available B2 prompts. |
| [`mq-agent b2 prompt`](#mq-agent-b2-prompt) | Print the full content of a B2 prompt by ID. |
| [`mq-agent b2 route`](#mq-agent-b2-route) | Route a topic to the matching B2 prompt route and primary prompt ID. |
| [`mq-agent b2 run`](#mq-agent-b2-run) | Run the B2 plan→compose→review→output workflow for a given context. |

## `mq-agent b2 history`

Show recent b2tui workflow run history.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--limit`, `-n` | No | `10` | — |
| `--json` | No | `false` | — |

## `mq-agent b2 list`

List available B2 prompts.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--category`, `-c` | No | `""` | Filter by category |
| `--json` | No | `false` | — |

## `mq-agent b2 prompt`

Print the full content of a B2 prompt by ID.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PROMPT_ID` | Yes | — | Prompt ID, e.g. 02.11 |

## `mq-agent b2 route`

Route a topic to the matching B2 prompt route and primary prompt ID.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `TOPIC` | Yes | — | Topic or context to route |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent b2 run`

Run the B2 plan→compose→review→output workflow for a given context.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `CONTEXT` | No | `""` | Topic or context for this workflow run |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--route`, `-r` | No | — | Force a specific route name |
| `--dry-run` | No | `false` | — |
| `--json` | No | `false` | — |

## `mq-agent brain`

Second brain vault commands (mqobsidian).

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent brain record-review`](#mq-agent-brain-record-review) | Write a review summary to mqobsidian/reviews/ via brain_record_review. Shell-friendly wrapper: accepts --top-risk and --next-step as repeatable options instead of list arguments, so any tool (zephyr, shell scripts) can call this without Python imports. |
| [`mq-agent brain structure`](#mq-agent-brain-structure) | Check the mqobsidian vault against the standard export structure. Read-only by default. --init --approve creates the missing standard directories (memory/stack-truth, memory/reviews, memory/learn, mq-stack/runs, mq-stack/roadmaps), each with a small README. Exit code 1 unless the structure is complete — usable as a gate. |

## `mq-agent brain record-review`

Write a review summary to mqobsidian/reviews/ via brain_record_review. Shell-friendly wrapper: accepts --top-risk and --next-step as repeatable options instead of list arguments, so any tool (zephyr, shell scripts) can call this without Python imports.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--source` | Yes | — | Review source identifier (e.g. zephyr:file.yaml) |
| `--top-risk` | No | — | Top risk finding (repeatable) |
| `--next-step` | No | — | Suggested next step (repeatable) |
| `--finding-count` | No | `0` | — |
| `--confidence` | No | `medium` | — |
| `--raw-summary` | No | `""` | — |
| `--approve` | No | `false` | — |
| `--json` | No | `false` | — |

## `mq-agent brain structure`

Check the mqobsidian vault against the standard export structure. Read-only by default. --init --approve creates the missing standard directories (memory/stack-truth, memory/reviews, memory/learn, mq-stack/runs, mq-stack/roadmaps), each with a small README. Exit code 1 unless the structure is complete — usable as a gate.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--init` | No | `false` | Create missing standard directories (write) |
| `--approve` | No | `false` | Required with --init |
| `--json` | No | `false` | — |

## `mq-agent browser`

Browser-safe URL inspection and release verification.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent browser inspect`](#mq-agent-browser-inspect) | Fetch a URL and show structured metadata: title, headings, links, word count. |
| [`mq-agent browser summarize`](#mq-agent-browser-summarize) | Fetch a URL and return a plain-text content summary. |
| [`mq-agent browser verify-release`](#mq-agent-browser-verify-release) | Inspect a release page and verify expected release fields are present. |

## `mq-agent browser inspect`

Fetch a URL and show structured metadata: title, headings, links, word count.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `URL` | Yes | — | URL to inspect |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |
| `--timeout` | No | `10` | — |

## `mq-agent browser summarize`

Fetch a URL and return a plain-text content summary.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `URL` | Yes | — | URL to summarize |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |
| `--timeout` | No | `10` | — |

## `mq-agent browser verify-release`

Inspect a release page and verify expected release fields are present.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `URL` | Yes | — | Release page URL to verify |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--tag` | No | `""` | Expected version tag (e.g. v0.7.0) |
| `--json` | No | `false` | — |
| `--timeout` | No | `10` | — |

## `mq-agent context`

Export compact repo-local .mq/context snapshots.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent context export`](#mq-agent-context-export) | Export small `.mq/context/` snapshots from mqobsidian context cards. This is Phase 4 orchestration: mqobsidian owns the card content; mq-agent selects repos and writes repo-local context files. Use `--output-root` for staging/tests before writing into real sibling repos. |
| [`mq-agent context pack`](#mq-agent-context-pack) | Generate a small task-specific `context-pack.v1` pack from mqobsidian cards. Phase 5 orchestration: mqobsidian owns the durable cards and the pack contract; mq-agent selects the relevant repos, cards, and do-not-read guidance for one task and adds an optional CodeGraph source-intelligence hint when the task is source-structure heavy. |

## `mq-agent context export`

Export small `.mq/context/` snapshots from mqobsidian context cards. This is Phase 4 orchestration: mqobsidian owns the card content; mq-agent selects repos and writes repo-local context files. Use `--output-root` for staging/tests before writing into real sibling repos.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--repo` | No | `""` | Repo name to export |
| `--all` | No | `false` | Export all core MQ repos |
| `--vault` | No | `""` | mqobsidian vault path (default: $MQ_OBSIDIAN_DIR or ~/mqobsidian) |
| `--output-root` | No | `""` | Repo root containing `<repo>`/ directories (default: ~) |
| `--target` | No | `both` | Compatibility flag for roadmap command shape: codex, claude, or both |
| `--dry-run` | No | `false` | Show what would be written without writing |
| `--clean` | No | `false` | Replace existing generated context directory before writing |
| `--json` | No | `false` | — |

## `mq-agent context pack`

Generate a small task-specific `context-pack.v1` pack from mqobsidian cards. Phase 5 orchestration: mqobsidian owns the durable cards and the pack contract; mq-agent selects the relevant repos, cards, and do-not-read guidance for one task and adds an optional CodeGraph source-intelligence hint when the task is source-structure heavy.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `TASK` | Yes | — | Short task description |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--repo` | No | `""` | Primary repo for the task |
| `--relevant-repo` | No | — | Extra relevant repo (repeatable) |
| `--relevant-file` | No | — | Extra relevant file/doc path (repeatable) |
| `--note` | No | — | Extra operator note (repeatable) |
| `--exclude` | No | — | Negative context as `kind:item[:reason]` where kind is forbidden\|fallback\|irrelevant (repeatable) |
| `--target` | No | `both` | codex, claude, or both |
| `--vault` | No | `""` | mqobsidian vault path (default: $MQ_OBSIDIAN_DIR or ~/mqobsidian) |
| `--repos-root` | No | `""` | Root holding `<repo>`/ dirs, used to detect .codegraph/ (default: ~) |
| `--codegraph` | No | `auto` | CodeGraph hint: auto (source-heavy only), on, or off |
| `--symbol` | No | — | Named symbol for a CodeGraph callers/impact query (repeatable) |
| `--output`, `--out` | No | `""` | Write the pack here instead of stdout |
| `--json` | No | `false` | — |

## `mq-agent dashboard`

Show the v1.19 operator dashboard snapshot.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent decide`

Record an architecture decision to mqobsidian/decisions/. Class C write.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `TITLE` | Yes | — | Short decision title |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--context`, `-c` | No | `""` | What prompted this decision |
| `--decision`, `-d` | No | `""` | What was decided |
| `--rationale`, `-r` | No | `""` | Why this decision was made |
| `--consequences` | No | `""` | Known trade-offs or follow-ups |
| `--tag` | No | — | Tag (repeatable) |
| `--json` | No | `false` | — |
| `--approve` | No | `false` | Required: decide is a write operation |

## `mq-agent docs-audit`

Audit repository documentation: README, CHANGELOG, docstrings, /docs.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | No | `.` | Repo path |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent doctor`

Check mq-agent environment and dependencies.

## `mq-agent fix-ci`

Diagnose CI failures and suggest fixes.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | No | `.` | — |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--dry-run` | No | `true` | — |
| `--approve` | No | `false` | — |
| `--json` | No | `false` | — |

## `mq-agent learn`

Learn commands — extraction, storage and promotion of review patterns.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent learn explain`](#mq-agent-learn-explain) | Fetch a detailed explanation of a learned pattern from mq-mcp. Read-only. |
| [`mq-agent learn extract-review`](#mq-agent-learn-extract-review) | Dry-run extraction of a learn candidate from the last review for a file. Read-only. |
| [`mq-agent learn from-diff`](#mq-agent-learn-from-diff) | Create a learning record with the current git diff as context. Class C write — requires --approve. |
| [`mq-agent learn from-review`](#mq-agent-learn-from-review) | Create a learning record from the last review for a file. Class C write — requires --approve. |
| [`mq-agent learn hygiene`](#mq-agent-learn-hygiene) | Show hygiene report for stored learning records. Read-only. |
| [`mq-agent learn promote`](#mq-agent-learn-promote) | Promote learn/`<slug>`.md to learn/verified/. Class C write — requires --approve. |
| [`mq-agent learn review-flow`](#mq-agent-learn-review-flow) | Review a file then extract a dry-run learn candidate in one pass. Read-only. |
| [`mq-agent learn search`](#mq-agent-learn-search) | Search mq-mcp learned review patterns. Read-only. |
| [`mq-agent learn status`](#mq-agent-learn-status) | Check availability of the mq-mcp learn system. Read-only. |
| [`mq-agent learn store`](#mq-agent-learn-store) | Store the last extracted learn candidate for a file. Class C write tool — requires --approve. |
| [`mq-agent learn summarize`](#mq-agent-learn-summarize) | Summarize stored learning records. Read-only. |

## `mq-agent learn explain`

Fetch a detailed explanation of a learned pattern from mq-mcp. Read-only.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATTERN_ID` | Yes | — | Pattern ID to explain |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent learn extract-review`

Dry-run extraction of a learn candidate from the last review for a file. Read-only.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | Yes | — | Repo-relative file path to extract a learn candidate from. |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--repo` | No | — | External repo path the file lives in (within mq-mcp allowlist) |
| `--json` | No | `false` | — |
| `--brain` | No | `false` | Record learn candidate to mqobsidian |
| `--dry-run` | No | `false` | Show what would be called, no execution |

## `mq-agent learn from-diff`

Create a learning record with the current git diff as context. Class C write — requires --approve.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--task`, `-t` | No | `""` | What was being done |
| `--lesson`, `-l` | No | `""` | What was learned |
| `--risk` | No | `low` | low \| medium \| high |
| `--validation` | No | `""` | How it was verified |
| `--approve` | No | `false` | Allow write to mq-mcp learn layer |
| `--dry-run` | No | `false` | — |
| `--json` | No | `false` | — |

## `mq-agent learn from-review`

Create a learning record from the last review for a file. Class C write — requires --approve.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | Yes | — | Repo-relative file path |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--task`, `-t` | No | `""` | What was being worked on |
| `--risk` | No | `low` | low \| medium \| high |
| `--repo` | No | — | External repo path the file lives in (within mq-mcp allowlist) |
| `--approve` | No | `false` | Allow write to mq-mcp learn layer |
| `--dry-run` | No | `false` | — |
| `--json` | No | `false` | — |

## `mq-agent learn hygiene`

Show hygiene report for stored learning records. Read-only.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent learn promote`

Promote learn/`<slug>`.md to learn/verified/. Class C write — requires --approve.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `SLUG` | Yes | — | Filename slug (without path or .md) |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--approve` | No | `false` | Allow write to mqobsidian vault |
| `--dry-run` | No | `false` | — |

## `mq-agent learn review-flow`

Review a file then extract a dry-run learn candidate in one pass. Read-only.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | Yes | — | Repo-relative file path |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--repo` | No | — | External repo path the file lives in (within mq-mcp allowlist) |
| `--json` | No | `false` | — |
| `--brain` | No | `false` | Record learn candidate to mqobsidian |
| `--dry-run` | No | `false` | Show what would be called, no execution |

## `mq-agent learn search`

Search mq-mcp learned review patterns. Read-only.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `QUERY` | Yes | — | Search query for learned patterns |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent learn status`

Check availability of the mq-mcp learn system. Read-only.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent learn store`

Store the last extracted learn candidate for a file. Class C write tool — requires --approve.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | Yes | — | Repo-relative file path |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--approve` | No | `false` | Allow write to mq-mcp |
| `--dry-run` | No | `false` | — |
| `--json` | No | `false` | — |

## `mq-agent learn summarize`

Summarize stored learning records. Read-only.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--limit` | No | `20` | Max number of records to include |
| `--json` | No | `false` | — |

## `mq-agent mcp`

Inspect and manage the local mq-mcp tool server.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent mcp connect`](#mq-agent-mcp-connect) | Register an external MCP server. |
| [`mq-agent mcp disconnect`](#mq-agent-mcp-disconnect) | Remove a registered MCP server. |
| [`mq-agent mcp start`](#mq-agent-mcp-start) | Start mq-mcp server in the background. |
| [`mq-agent mcp status`](#mq-agent-mcp-status) | Check whether MCP servers are reachable and show tool counts. |
| [`mq-agent mcp stop`](#mq-agent-mcp-stop) | Stop the background mq-mcp server. |
| [`mq-agent mcp tools`](#mq-agent-mcp-tools) | List all tools discovered from all connected MCP servers. |

## `mq-agent mcp connect`

Register an external MCP server.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `NAME` | Yes | — | Server name (e.g. RepoPrompt) |
| `URL` | Yes | — | MCP server URL (e.g. `http://localhost:PORT`) |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent mcp disconnect`

Remove a registered MCP server.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `NAME` | Yes | — | Server name to remove |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent mcp start`

Start mq-mcp server in the background.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent mcp status`

Check whether MCP servers are reachable and show tool counts.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent mcp stop`

Stop the background mq-mcp server.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent mcp tools`

List all tools discovered from all connected MCP servers.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent memory`

Semantic repository memory commands.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent memory build`](#mq-agent-memory-build) | Upload semantic repo memory via repo-signal. Dry-run by default. |
| [`mq-agent memory doctor`](#mq-agent-memory-doctor) | Diagnose semantic memory environment. |
| [`mq-agent memory emit-cochange`](#mq-agent-memory-emit-cochange) | Emit one co-change memory-observation.v1 from Bridget/CG-2 evidence. mq-agent is the producer; Bridget/CG-2 is the evidence source. Writes nothing when no co-change cluster clears the gate. mqobsidian scores and promotes. |
| [`mq-agent memory inbox-cochange`](#mq-agent-memory-inbox-cochange) | Operator-triggered co-change intake: emit → score → writeback → status. Runs the autonomous learning loop end-to-end for one file, but only when you ask (not auto-after-workflow). mq-agent orchestrates; Bridget/CG-2 is evidence source; mqobsidian owns scoring/writeback/status (invoked via its own local-only CLI). |
| [`mq-agent memory ingest`](#mq-agent-memory-ingest) | Scan mqobsidian memory notes into a local read-only index. |
| [`mq-agent memory learn-writeback`](#mq-agent-memory-learn-writeback) | Materialise durable agent-readable memory for PROMOTED memories. Dry-run by default. inbox-cochange runs this as stage 4 of intake; this is the same verb standalone, for promotions that landed another way. mqobsidian decides what counts as promoted — candidate and observed memories are never written. |
| [`mq-agent memory link`](#mq-agent-memory-link) | Infer read-only link candidates between mqobsidian notes. |
| [`mq-agent memory promote-from-review`](#mq-agent-memory-promote-from-review) | Approve a held promotion-review memory → promote it (co-change never auto-promotes). Appends a promotion-event + directive snapshot via mqobsidian's CLI. Dry-run by default. |
| [`mq-agent memory query`](#mq-agent-memory-query) | Search mqobsidian memory notes. Alias: search-vault. |
| [`mq-agent memory refresh`](#mq-agent-memory-refresh) | Refresh semantic repo memory. Requires --approve to upload. |
| [`mq-agent memory resolve-supersede`](#mq-agent-memory-resolve-supersede) | Accept or reject a deep-conflict supersede proposal (exactly one of --accept/--reject). |
| [`mq-agent memory review-status`](#mq-agent-memory-review-status) | Show the mqobsidian scoring review state: tier tally + held review queues (read-only). Delegates to mqobsidian's local-only CLI; mq-agent stays the orchestrator so mqlaunch never reaches mqobsidian directly. |
| [`mq-agent memory search`](#mq-agent-memory-search) | Search mq-mcp semantic memory. Read-only. Requires mq-mcp v1.4.0+. |
| [`mq-agent memory search-vault`](#mq-agent-memory-search-vault) | Search mqobsidian memory notes. Alias: search-vault. |
| [`mq-agent memory status`](#mq-agent-memory-status) | Check semantic repository memory availability. |
| [`mq-agent memory store`](#mq-agent-memory-store) | Store an item in mq-mcp semantic memory. Class C write tool — requires --approve. |
| [`mq-agent memory summarize`](#mq-agent-memory-summarize) | Summarize mqobsidian memory by section. |

## `mq-agent memory build`

Upload semantic repo memory via repo-signal. Dry-run by default.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | No | `.` | Repo path |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--dry-run`, `--no-dry-run` | No | `true` | — |

## `mq-agent memory doctor`

Diagnose semantic memory environment.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | No | `.` | Repo path |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent memory emit-cochange`

Emit one co-change memory-observation.v1 from Bridget/CG-2 evidence. mq-agent is the producer; Bridget/CG-2 is the evidence source. Writes nothing when no co-change cluster clears the gate. mqobsidian scores and promotes.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `REPO` | Yes | — | Path to the repo to analyze |
| `FILE` | Yes | — | File to find co-change clusters for |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--window` | No | `300` | Commits to scan |
| `--min-confidence` | No | `0.05` | Cluster confidence gate (weak-signal intake; default low) |
| `--min-support` | No | `2` | Min co-change count |
| `--vault` | No | — | mqobsidian vault path |

## `mq-agent memory inbox-cochange`

Operator-triggered co-change intake: emit → score → writeback → status. Runs the autonomous learning loop end-to-end for one file, but only when you ask (not auto-after-workflow). mq-agent orchestrates; Bridget/CG-2 is evidence source; mqobsidian owns scoring/writeback/status (invoked via its own local-only CLI).

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `REPO` | Yes | — | Path to the repo to analyze |
| `FILE` | Yes | — | File to find co-change clusters for |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--window` | No | `300` | Commits to scan |
| `--min-confidence` | No | `0.05` | Cluster confidence gate (weak-signal intake) |
| `--min-support` | No | `2` | Min co-change count |
| `--vault` | No | — | mqobsidian vault path (or $MQ_OBSIDIAN_DIR) |
| `--dry-run` | No | `false` | Write nothing; show what would happen |
| `--no-writeback` | No | `false` | Score but do not write learn files |

## `mq-agent memory ingest`

Scan mqobsidian memory notes into a local read-only index.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--vault` | No | — | mqobsidian vault path |
| `--json` | No | `false` | — |

## `mq-agent memory learn-writeback`

Materialise durable agent-readable memory for PROMOTED memories. Dry-run by default. inbox-cochange runs this as stage 4 of intake; this is the same verb standalone, for promotions that landed another way. mqobsidian decides what counts as promoted — candidate and observed memories are never written.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--apply` | No | `false` | Persist the writeback (default: dry-run) |
| `--vault` | No | — | mqobsidian vault path (or $MQ_OBSIDIAN_DIR) |

## `mq-agent memory link`

Infer read-only link candidates between mqobsidian notes.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--vault` | No | — | mqobsidian vault path |
| `--limit` | No | `20` | — |
| `--json` | No | `false` | — |

## `mq-agent memory promote-from-review`

Approve a held promotion-review memory → promote it (co-change never auto-promotes). Appends a promotion-event + directive snapshot via mqobsidian's CLI. Dry-run by default.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `MEMORY_ID` | Yes | — | memory_id held in the promotion-review queue |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--apply` | No | `false` | Persist the promotion (default: dry-run) |
| `--vault` | No | — | mqobsidian vault path (or $MQ_OBSIDIAN_DIR) |

## `mq-agent memory query`

Search mqobsidian memory notes. Alias: search-vault.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `QUERY` | Yes | — | Search query |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--vault` | No | — | mqobsidian vault path |
| `--limit` | No | `10` | — |
| `--json` | No | `false` | — |

## `mq-agent memory refresh`

Refresh semantic repo memory. Requires --approve to upload.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | No | `.` | Repo path |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--approve` | No | `false` | Allow upload |

## `mq-agent memory resolve-supersede`

Accept or reject a deep-conflict supersede proposal (exactly one of --accept/--reject).

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `MEMORY_ID` | Yes | — | memory_id with an open supersede proposal |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--accept` | No | `false` | Adopt the new directive as authoritative |
| `--reject` | No | `false` | Keep the promoted directive; dismiss the conflict |
| `--apply` | No | `false` | Persist the resolution (default: dry-run) |
| `--vault` | No | — | mqobsidian vault path (or $MQ_OBSIDIAN_DIR) |

## `mq-agent memory review-status`

Show the mqobsidian scoring review state: tier tally + held review queues (read-only). Delegates to mqobsidian's local-only CLI; mq-agent stays the orchestrator so mqlaunch never reaches mqobsidian directly.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--vault` | No | — | mqobsidian vault path (or $MQ_OBSIDIAN_DIR) |

## `mq-agent memory search`

Search mq-mcp semantic memory. Read-only. Requires mq-mcp v1.4.0+.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `QUERY` | Yes | — | Search query |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent memory search-vault`

Search mqobsidian memory notes. Alias: search-vault.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `QUERY` | Yes | — | Search query |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--vault` | No | — | mqobsidian vault path |
| `--limit` | No | `10` | — |
| `--json` | No | `false` | — |

## `mq-agent memory status`

Check semantic repository memory availability.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | No | `.` | Repo path |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent memory store`

Store an item in mq-mcp semantic memory. Class C write tool — requires --approve.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `KEY` | Yes | — | Memory key |
| `VALUE` | Yes | — | Memory value |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--approve` | No | `false` | Allow write to mq-mcp |
| `--dry-run` | No | `false` | — |
| `--json` | No | `false` | — |

## `mq-agent memory summarize`

Summarize mqobsidian memory by section.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--vault` | No | — | mqobsidian vault path |
| `--json` | No | `false` | — |

## `mq-agent models`

Ollama model runtime commands.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent models bench`](#mq-agent-models-bench) | Benchmark a local Ollama model with timing and token metrics. |
| [`mq-agent models current`](#mq-agent-models-current) | Show the active model profile. |
| [`mq-agent models doctor`](#mq-agent-models-doctor) | Run read-only diagnostics for Ollama, model profiles, and mq-learn. |
| [`mq-agent models list`](#mq-agent-models-list) | List locally available Ollama models. |
| [`mq-agent models switch`](#mq-agent-models-switch) | Switch the active profile, or assign a model to a profile. |

## `mq-agent models bench`

Benchmark a local Ollama model with timing and token metrics.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `MODEL` | No | — | Model name; defaults to active model |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--prompt` | No | `Reply with OK.` | Benchmark prompt |
| `--timeout` | No | `30` | Ollama timeout in seconds |
| `--keep-alive` | No | `0` | Ollama keep_alive value |
| `--json` | No | `false` | — |

## `mq-agent models current`

Show the active model profile.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent models doctor`

Run read-only diagnostics for Ollama, model profiles, and mq-learn.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--smoke`, `--no-smoke` | No | `true` | Run mq-learn JSON smoke test |
| `--timeout` | No | `60` | Smoke-test timeout in seconds |
| `--json` | No | `false` | — |

## `mq-agent models list`

List locally available Ollama models.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent models switch`

Switch the active profile, or assign a model to a profile.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `TARGET` | Yes | — | Profile or model name |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--profile` | No | — | Assign model to this profile |
| `--approve` | No | `false` | Write ~/.mq-agent/models.json |
| `--json` | No | `false` | — |

## `mq-agent obsidian`

Read and action the mqobsidian promotion inbox.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent obsidian defer`](#mq-agent-obsidian-defer) | Defer a candidate (candidate -> observed). No durable learn record. |
| [`mq-agent obsidian deprecate`](#mq-agent-obsidian-deprecate) | Deprecate a promoted memory (promoted -> deprecated). Retains the record. |
| [`mq-agent obsidian inbox`](#mq-agent-obsidian-inbox) | Read the canonical mqobsidian promotion inbox (read-only). |
| [`mq-agent obsidian promote`](#mq-agent-obsidian-promote) | Promote a candidate (candidate -> promoted). Requires traceable source evidence. |
| [`mq-agent obsidian reject`](#mq-agent-obsidian-reject) | Reject a candidate (candidate -> archived). No durable learn record. |
| [`mq-agent obsidian rollback`](#mq-agent-obsidian-rollback) | Roll back a promotion (promoted -> candidate). Removes the generated learn projection. |

## `mq-agent obsidian defer`

Defer a candidate (candidate -> observed). No durable learn record.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `MEMORY_ID` | Yes | — | Candidate memory_id |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--reason` | Yes | — | Why this candidate is deferred |
| `--confirm` | No | `false` | Apply the transition (default: dry-run) |
| `--json` | No | `false` | Machine-readable output |
| `--vault` | No | — | mqobsidian vault path (or $MQ_OBSIDIAN_DIR) |

## `mq-agent obsidian deprecate`

Deprecate a promoted memory (promoted -> deprecated). Retains the record.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `MEMORY_ID` | Yes | — | Promoted memory_id |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--reason` | Yes | — | Why this memory is deprecated |
| `--confirm` | No | `false` | Apply the transition (default: dry-run) |
| `--json` | No | `false` | Machine-readable output |
| `--vault` | No | — | mqobsidian vault path (or $MQ_OBSIDIAN_DIR) |

## `mq-agent obsidian inbox`

Read the canonical mqobsidian promotion inbox (read-only).

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent obsidian inbox list`](#mq-agent-obsidian-inbox-list) | List promotion candidates from mqobsidian's canonical inbox export (read-only). |
| [`mq-agent obsidian inbox rank`](#mq-agent-obsidian-inbox-rank) | Rank candidates under mqobsidian's promotion policy (inbox_promotion_orchestration.v1). `auto-promotable` means eligible for approval — never an unattended write. |
| [`mq-agent obsidian inbox read`](#mq-agent-obsidian-inbox-read) | Read one promotion candidate. Exits 1 when the candidate is not in the inbox. |

## `mq-agent obsidian inbox list`

List promotion candidates from mqobsidian's canonical inbox export (read-only).

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | Machine-readable output |
| `--vault` | No | — | mqobsidian vault path (or $MQ_OBSIDIAN_DIR) |

## `mq-agent obsidian inbox rank`

Rank candidates under mqobsidian's promotion policy (inbox_promotion_orchestration.v1). `auto-promotable` means eligible for approval — never an unattended write.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | Machine-readable output |
| `--vault` | No | — | mqobsidian vault path (or $MQ_OBSIDIAN_DIR) |

## `mq-agent obsidian inbox read`

Read one promotion candidate. Exits 1 when the candidate is not in the inbox.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `MEMORY_ID` | Yes | — | Candidate memory_id |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | Machine-readable output |
| `--vault` | No | — | mqobsidian vault path (or $MQ_OBSIDIAN_DIR) |

## `mq-agent obsidian promote`

Promote a candidate (candidate -> promoted). Requires traceable source evidence.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `MEMORY_ID` | Yes | — | Candidate memory_id |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--reason` | Yes | — | Why this promotion is justified |
| `--evidence` | No | — | Published evidence ref (repeatable) |
| `--confirm` | No | `false` | Apply the transition (default: dry-run) |
| `--json` | No | `false` | Machine-readable output |
| `--vault` | No | — | mqobsidian vault path (or $MQ_OBSIDIAN_DIR) |

## `mq-agent obsidian reject`

Reject a candidate (candidate -> archived). No durable learn record.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `MEMORY_ID` | Yes | — | Candidate memory_id |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--reason` | Yes | — | Why this candidate is rejected |
| `--confirm` | No | `false` | Apply the transition (default: dry-run) |
| `--json` | No | `false` | Machine-readable output |
| `--vault` | No | — | mqobsidian vault path (or $MQ_OBSIDIAN_DIR) |

## `mq-agent obsidian rollback`

Roll back a promotion (promoted -> candidate). Removes the generated learn projection.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `MEMORY_ID` | Yes | — | Promoted memory_id |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--reason` | Yes | — | Why this promotion is rolled back |
| `--confirm` | No | `false` | Apply the transition (default: dry-run) |
| `--json` | No | `false` | Machine-readable output |
| `--vault` | No | — | mqobsidian vault path (or $MQ_OBSIDIAN_DIR) |

## `mq-agent plan`

Create a plan for a goal using the AI planner.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `GOAL` | Yes | — | Goal to plan |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent release-check`

Validate the repo is ready for a release.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | No | `.` | Repo path |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--dry-run` | No | `true` | — |
| `--approve` | No | `false` | Allow write operations |
| `--json` | No | `false` | — |

## `mq-agent release-plan`

Show the standard release plan.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent repo-summary`

Print a concise repo summary.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | No | `.` | — |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent review`

Pass-through mq-mcp review orchestration.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent review diff`](#mq-agent-review-diff) | Review the current diff through mq-mcp. Findings are passed through. |
| [`mq-agent review file`](#mq-agent-review-file) | Review one file through mq-mcp. mq-agent does not implement review logic. |
| [`mq-agent review repo`](#mq-agent-review-repo) | Review a repo through mq-mcp. mq-agent renders mq-mcp output only. |

## `mq-agent review diff`

Review the current diff through mq-mcp. Findings are passed through.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--security` | No | `false` | Ask mq-mcp for security review mode |
| `--architecture` | No | `false` | Ask mq-mcp for architecture review mode |
| `--architecture-image`, `--visual` | No | — | Image path to observe via mq-image-analyze and pass as architecture context |
| `--risk` | No | `false` | Use mq-mcp risk review when installed |
| `--fast` | No | `false` | Prefer fast Class A tools over deep AI review |
| `--brain` | No | `false` | Record review result to mqobsidian second brain |
| `--json` | No | `false` | — |
| `--dry-run` | No | `false` | Show what would be called, no execution |

## `mq-agent review file`

Review one file through mq-mcp. mq-agent does not implement review logic.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | Yes | — | File path to review |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--security` | No | `false` | Ask mq-mcp for security review mode |
| `--architecture` | No | `false` | Ask mq-mcp for architecture review mode |
| `--architecture-image`, `--visual` | No | — | Image path to observe via mq-image-analyze and pass as architecture context |
| `--risk` | No | `false` | Use mq-mcp risk review when installed |
| `--fast` | No | `false` | Prefer fast Class A tools over deep AI review |
| `--brain` | No | `false` | Record review result to mqobsidian second brain |
| `--repo` | No | — | External repo path the file lives in (within mq-mcp allowlist) |
| `--json` | No | `false` | — |
| `--dry-run` | No | `false` | Show what would be called, no execution |

## `mq-agent review repo`

Review a repo through mq-mcp. mq-agent renders mq-mcp output only.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | No | `.` | Repo path to review |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--security` | No | `false` | Ask mq-mcp for security review mode |
| `--architecture` | No | `false` | Ask mq-mcp for architecture review mode |
| `--architecture-image`, `--visual` | No | — | Image path to observe via mq-image-analyze and pass as architecture context |
| `--risk` | No | `false` | Use mq-mcp risk review when installed |
| `--fast` | No | `false` | Prefer fast Class A tools over deep AI review |
| `--brain` | No | `false` | Record review result to mqobsidian second brain |
| `--json` | No | `false` | — |
| `--dry-run` | No | `false` | Show what would be called, no execution |

## `mq-agent route`

Inspect advisory local-first model routing.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent route evidence-review`](#mq-agent-route-evidence-review) | Review one task class without promoting it or changing routing policy. |
| [`mq-agent route history`](#mq-agent-route-history) | List individual routing outcomes newest first, read-only. |
| [`mq-agent route inspect`](#mq-agent-route-inspect) | Recommend a route without model calls or writes. |
| [`mq-agent route report`](#mq-agent-route-report) | Aggregate validated routing outcomes from a read-only source. |
| [`mq-agent route shadow`](#mq-agent-route-shadow) | Run and verify an advisory Ollama candidate without accepting it. |

## `mq-agent route evidence-review`

Review one task class without promoting it or changing routing policy.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `TASK_CLASS` | Yes | — | Task class to review for promotion |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--source` | No | — | JSON or JSONL outcome source |
| `--json` | No | `false` | — |

## `mq-agent route history`

List individual routing outcomes newest first, read-only.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--source` | No | — | JSON or JSONL outcome source |
| `--decision-id` | No | — | Explain a single routing decision |
| `--task-class` | No | — | Limit history to one task class |
| `--limit` | No | `20` | Newest entries to return; 0 returns all |
| `--json` | No | `false` | — |

## `mq-agent route inspect`

Recommend a route without model calls or writes.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `TASK` | Yes | — | Task to classify |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--agent` | No | `codex` | Authoritative coding agent: codex or claude |
| `--json` | No | `false` | — |

## `mq-agent route report`

Aggregate validated routing outcomes from a read-only source.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--source` | No | — | JSON or JSONL outcome source |
| `--json` | No | `false` | — |

## `mq-agent route shadow`

Run and verify an advisory Ollama candidate without accepting it.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `TASK` | Yes | — | Task for advisory local evaluation |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--agent` | No | `codex` | Authoritative coding agent: codex or claude |
| `--timeout` | No | `180` | Ollama timeout in seconds |
| `--context-file` | No | — | Material the candidate must quote verbatim; enables grounding verification |
| `--json` | No | `false` | — |

## `mq-agent run`

Run a shell command safely, or the canonical stack runtime with --stack.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `COMMAND` | No | `""` | Shell command to run |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--cwd` | No | `.` | — |
| `--dry-run` | No | `false` | — |
| `--approve` | No | `false` | Execute the command |
| `--stack` | No | `false` | Run the canonical stack runtime pipeline |
| `--json` | No | `false` | — |
| `--markdown` | No | `false` | Render --stack runtime result as Markdown |
| `--brain` | No | `false` | Write stack truth export when combined with --approve and --stack |
| `--ci` | No | `false` | CI mode for --stack runtime gates |

## `mq-agent run-tool`

Run a specific MCP tool through mq-agent safety gates.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `TOOL` | Yes | — | MCP tool name to run |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--arg` | No | — | key=value argument (repeatable) |
| `--dry-run` | No | `false` | Preview without executing |
| `--approve` | No | `false` | Allow write-capable and subprocess tools |
| `--dangerous` | No | `false` | Allow dangerous-class tools |
| `--json` | No | `false` | — |

## `mq-agent score`

Quick README score (0–100) and publish checklist — no AI, instant result. Requires repo-signal to be installed: uv pip install repo-signal

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | No | `.` | Repo path |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent ship`

Inspect release state, proof, and audit evidence (read-only).

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent ship audit`](#mq-agent-ship-audit) | Audit a published release; exits non-zero unless all evidence passes. |
| [`mq-agent ship proof`](#mq-agent-ship-proof) | Show bounded release evidence for the current or selected release. |
| [`mq-agent ship status`](#mq-agent-ship-status) | Answer whether the selected repository can be released safely now. |

## `mq-agent ship audit`

Audit a published release; exits non-zero unless all evidence passes.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--repo` | No | `.` | Repository path |
| `--target` | No | — | Target version without v prefix |
| `--json` | No | `false` | — |

## `mq-agent ship proof`

Show bounded release evidence for the current or selected release.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--repo` | No | `.` | Repository path |
| `--target` | No | — | Target version without v prefix |
| `--json` | No | `false` | — |

## `mq-agent ship status`

Answer whether the selected repository can be released safely now.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--repo` | No | `.` | Repository path |
| `--target` | No | — | Target version without v prefix |
| `--json` | No | `false` | — |

## `mq-agent signal`

Run a full repo-signal assessment: scan + README score + publish checklist + AI plan. Requires repo-signal to be installed: uv pip install repo-signal

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | No | `.` | Repo path to analyse |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--dry-run` | No | `false` | — |
| `--json` | No | `false` | — |
| `--brain` | No | `false` | Record signal result to mqobsidian second brain |

## `mq-agent stack`

mq-stack repo inventory, status, and Obsidian export.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent stack alert`](#mq-agent-stack-alert) | Warn when a repo dropped >= threshold points or is below min-score since the last sweep. Exits 0 when no alerts, exits 1 when alerts are found (CI-friendly). |
| [`mq-agent stack brain-gate`](#mq-agent-stack-brain-gate) | Brain release gate: contract-check + release-check + truth-export dry-run + vault structure + the review→brain write path, all green before a release. Read-only; exit 1 on NO-GO. |
| [`mq-agent stack cockpit`](#mq-agent-stack-cockpit) | One-table stack cockpit: repo, version, branch, dirty, contract, release gate, unreleased work, brain-export freshness and next action. Read-only — combines stack status, contract-check, release-check and the latest mqobsidian stack-truth note into a single view. Later the input to mq-hal. |
| [`mq-agent stack compatibility`](#mq-agent-stack-compatibility) | Assess dependency compatibility across MQ repositories (read-only). A repo can be green while the stack holds a latent incompatibility: an unbounded range, or a lockfile masking what a fresh install would pick. This reads declared and locked versions with provenance and never modifies dependencies, lockfiles or working trees. --fresh-resolve answers what a new installation would select today. It resolves outside every working tree, never reads or writes a lockfile, and reports an unreachable registry as UNAVAILABLE rather than incompatibility. Exit codes: 0 PASS or WARN, 2 FAIL, 3 UNAVAILABLE. |
| [`mq-agent stack contract-check`](#mq-agent-stack-contract-check) | Validate that every mq-stack repo declares a contract manifest. Reads .mq/repo-contract.json per repo and checks VERSION sync. No API key required. Exits 1 if any repo is BLOCKED or DRIFT. With --ci, repos missing from the workspace are SKIPPED instead of BLOCKED — the CI checkout itself is still fully validated. |
| [`mq-agent stack export`](#mq-agent-stack-export) | Write the mq-stack truth snapshot (contract + release gates) to mqobsidian. Primary name: `stack truth-export`. `stack export` is kept as a backwards-compatible alias — both run the same export. Pass ``--rebuild-views`` to refresh agent views at the end of the workflow (opt-in — see docs/AGENT_VIEW_CONTRACT.md phase C). |
| [`mq-agent stack history`](#mq-agent-stack-history) | Show repo health scores from past stack sweeps. |
| [`mq-agent stack loop`](#mq-agent-stack-loop) | Plan or execute one v1.20 controlled autonomous stack loop. Dry-run by default. `--execute --approve` runs one allowlisted action with command-specific rollback behaviour. |
| [`mq-agent stack release`](#mq-agent-stack-release) | Orchestrated single-repo release: gate, bump, changelog, tag, push, truth-export. Dry-run by default — shows the plan without touching the repo. With --execute the plan is applied step by step; any failed step aborts the run and pre-commit file edits are rolled back. Exits 1 on NO-GO or on a failed step. Ends with a stack truth-export so the release lands in mqobsidian memory. With --all, plans a release for every stack repo at once (dry-run by default): each repo is reported as ready, blocked, or up-to-date. Exits 1 if any repo is blocked. Release a ready repo with --repo `<name>` --execute. With --all --preflight, runs the read-only multi-repo release preflight: the strict fail-fast refusal surface (dirty, off-main, unpushed, tag exists, version mismatch, and each repo's release-check.sh). Never mutates and never executes; exits 1 if any repo is blocked. Pull-request repos stop in AWAITING_MERGE without directly releasing other repos. Finalize a verified merged release PR explicitly with --finalize-pr, --repo, --version and --approve. |
| [`mq-agent stack release-check`](#mq-agent-stack-release-check) | Run release-readiness checks across all mq-stack repos. Checks per repo: VERSION file, CHANGELOG entry, clean working tree, on main/master branch. No API key required. Exits 1 on any blocker. With --ci, sibling repos missing from the workspace are skipped instead of blocking — only repos that are present (e.g. the CI checkout) gate. |
| [`mq-agent stack release-notes`](#mq-agent-stack-release-notes) | Draft release notes from git commits since the last tag, per repo. Reads git log since last tag for each mq-stack repo. No API key required. Always exits 0 (informational). |
| [`mq-agent stack report`](#mq-agent-stack-report) | Consolidated stack health view: score, trend, alert and readiness per repo. Reads sweep history for scores and trend; no API key required. |
| [`mq-agent stack run`](#mq-agent-stack-run) | Run the v1.16 stack runtime gate. Checks repo-signal, mq-mcp, Ollama, brain export rendering and release readiness in one operator-facing pass. Read-only by default; `--brain` writes the truth export only when `--approve` is also supplied. |
| [`mq-agent stack skills-check`](#mq-agent-stack-skills-check) | Validate skill consistency across every mq-stack repo. Runs each repo's scripts/check-skills.sh (frontmatter, skill cross-references, referenced paths, SKILLS.md sync). No API key required. Exits 1 if any repo is DRIFT (skills inconsistent) or BLOCKED. With --ci, repos missing from the workspace are SKIPPED. |
| [`mq-agent stack status`](#mq-agent-stack-status) | Show version, branch, last activity, drift risk and readiness for all mq-stack repos. |
| [`mq-agent stack sweep`](#mq-agent-stack-sweep) | Run repo-signal over every mq-stack repo and optionally write brain notes + an ADR snapshot. For each reachable repo: runs mq-agent signal --brain (read + optional write). With --decide: writes a brain ADR via mq-agent decide capturing overall health. With --alert: exits 1 if any repo dropped >= threshold points or is below 80. |
| [`mq-agent stack truth-export`](#mq-agent-stack-truth-export) | Write the mq-stack truth snapshot (contract + release gates) to mqobsidian. Primary name: `stack truth-export`. `stack export` is kept as a backwards-compatible alias — both run the same export. Pass ``--rebuild-views`` to refresh agent views at the end of the workflow (opt-in — see docs/AGENT_VIEW_CONTRACT.md phase C). |

## `mq-agent stack alert`

Warn when a repo dropped >= threshold points or is below min-score since the last sweep. Exits 0 when no alerts, exits 1 when alerts are found (CI-friendly).

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--threshold`, `-t` | No | `10` | Point drop that triggers an alert |
| `--min-score` | No | `80` | Score below this always alerts |
| `--json` | No | `false` | — |

## `mq-agent stack brain-gate`

Brain release gate: contract-check + release-check + truth-export dry-run + vault structure + the review→brain write path, all green before a release. Read-only; exit 1 on NO-GO.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent stack cockpit`

One-table stack cockpit: repo, version, branch, dirty, contract, release gate, unreleased work, brain-export freshness and next action. Read-only — combines stack status, contract-check, release-check and the latest mqobsidian stack-truth note into a single view. Later the input to mq-hal.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent stack compatibility`

Assess dependency compatibility across MQ repositories (read-only). A repo can be green while the stack holds a latent incompatibility: an unbounded range, or a lockfile masking what a fresh install would pick. This reads declared and locked versions with provenance and never modifies dependencies, lockfiles or working trees. --fresh-resolve answers what a new installation would select today. It resolves outside every working tree, never reads or writes a lockfile, and reports an unreachable registry as UNAVAILABLE rather than incompatibility. Exit codes: 0 PASS or WARN, 2 FAIL, 3 UNAVAILABLE.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |
| `--all` | No | `false` | Inventory the whole stack instead of the MCP slice |
| `--fresh-resolve` | No | `false` | Also resolve declared ranges in a temporary directory and probe critical imports (needs uv and network) |

## `mq-agent stack contract-check`

Validate that every mq-stack repo declares a contract manifest. Reads .mq/repo-contract.json per repo and checks VERSION sync. No API key required. Exits 1 if any repo is BLOCKED or DRIFT. With --ci, repos missing from the workspace are SKIPPED instead of BLOCKED — the CI checkout itself is still fully validated.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |
| `--ci` | No | `false` | CI mode: skip repos missing from the workspace |

## `mq-agent stack export`

Write the mq-stack truth snapshot (contract + release gates) to mqobsidian. Primary name: `stack truth-export`. `stack export` is kept as a backwards-compatible alias — both run the same export. Pass ``--rebuild-views`` to refresh agent views at the end of the workflow (opt-in — see docs/AGENT_VIEW_CONTRACT.md phase C).

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--output`, `-o` | No | `""` | Output path (default: dated note under mqobsidian/memory/stack-truth/) |
| `--dry-run` | No | `false` | — |
| `--json` | No | `false` | — |
| `--rebuild-views` | No | `false` | Also rebuild agent views after export (opt-in, off by default) |

## `mq-agent stack history`

Show repo health scores from past stack sweeps.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--limit`, `-n` | No | `5` | Number of past sweeps to show |
| `--diff` | No | `false` | Diff the two most recent sweeps |
| `--json` | No | `false` | — |

## `mq-agent stack loop`

Plan or execute one v1.20 controlled autonomous stack loop. Dry-run by default. `--execute --approve` runs one allowlisted action with command-specific rollback behaviour.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--dry-run` | No | `true` | Plan only; do not execute the selected loop action |
| `--execute` | No | `false` | Execute one allowlisted loop action; requires --approve |
| `--json` | No | `false` | — |
| `--approve` | No | `false` | Approve controlled execution for one allowlisted action |
| `--max-iterations` | No | `1` | Bounded loop count for the plan |

## `mq-agent stack release`

Orchestrated single-repo release: gate, bump, changelog, tag, push, truth-export. Dry-run by default — shows the plan without touching the repo. With --execute the plan is applied step by step; any failed step aborts the run and pre-commit file edits are rolled back. Exits 1 on NO-GO or on a failed step. Ends with a stack truth-export so the release lands in mqobsidian memory. With --all, plans a release for every stack repo at once (dry-run by default): each repo is reported as ready, blocked, or up-to-date. Exits 1 if any repo is blocked. Release a ready repo with --repo `<name>` --execute. With --all --preflight, runs the read-only multi-repo release preflight: the strict fail-fast refusal surface (dirty, off-main, unpushed, tag exists, version mismatch, and each repo's release-check.sh). Never mutates and never executes; exits 1 if any repo is blocked. Pull-request repos stop in AWAITING_MERGE without directly releasing other repos. Finalize a verified merged release PR explicitly with --finalize-pr, --repo, --version and --approve.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--repo` | No | `""` | Stack repo to release |
| `--all` | No | `false` | Plan or execute a release across every stack repo |
| `--bump` | No | `patch` | Version bump: patch, minor or major |
| `--version` | No | `""` | Explicit target version (overrides --bump) |
| `--execute` | No | `false` | Apply the release (default is dry-run) |
| `--approve` | No | `false` | Required with --all --execute: multi-repo release is a write flow |
| `--finalize-pr` | No | `0` | Finalize a merged release PR by number; requires --repo, --version and --approve |
| `--preflight` | No | `false` | Read-only multi-repo release preflight (strict blockers; never executes). Requires --all. |
| `--json` | No | `false` | — |

## `mq-agent stack release-check`

Run release-readiness checks across all mq-stack repos. Checks per repo: VERSION file, CHANGELOG entry, clean working tree, on main/master branch. No API key required. Exits 1 on any blocker. With --ci, sibling repos missing from the workspace are skipped instead of blocking — only repos that are present (e.g. the CI checkout) gate.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--dry-run` | No | `false` | — |
| `--json` | No | `false` | — |
| `--ci` | No | `false` | CI mode: skip repos missing from the workspace |

## `mq-agent stack release-notes`

Draft release notes from git commits since the last tag, per repo. Reads git log since last tag for each mq-stack repo. No API key required. Always exits 0 (informational).

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--repo` | No | — | Limit to one repo |
| `--json` | No | `false` | — |

## `mq-agent stack report`

Consolidated stack health view: score, trend, alert and readiness per repo. Reads sweep history for scores and trend; no API key required.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent stack run`

Run the v1.16 stack runtime gate. Checks repo-signal, mq-mcp, Ollama, brain export rendering and release readiness in one operator-facing pass. Read-only by default; `--brain` writes the truth export only when `--approve` is also supplied.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--dry-run` | No | `false` | — |
| `--json` | No | `false` | — |
| `--markdown` | No | `false` | Render the runtime result as Markdown |
| `--brain` | No | `false` | Write the stack truth export when combined with --approve |
| `--ci` | No | `false` | CI mode: skip repos missing from the workspace in release gates |
| `--approve` | No | `false` | Allow write steps requested by --brain |

## `mq-agent stack skills-check`

Validate skill consistency across every mq-stack repo. Runs each repo's scripts/check-skills.sh (frontmatter, skill cross-references, referenced paths, SKILLS.md sync). No API key required. Exits 1 if any repo is DRIFT (skills inconsistent) or BLOCKED. With --ci, repos missing from the workspace are SKIPPED.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |
| `--ci` | No | `false` | CI mode: skip repos missing from the workspace |

## `mq-agent stack status`

Show version, branch, last activity, drift risk and readiness for all mq-stack repos.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent stack sweep`

Run repo-signal over every mq-stack repo and optionally write brain notes + an ADR snapshot. For each reachable repo: runs mq-agent signal --brain (read + optional write). With --decide: writes a brain ADR via mq-agent decide capturing overall health. With --alert: exits 1 if any repo dropped >= threshold points or is below 80.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--brain` | No | `false` | Record signal result for each repo to mqobsidian |
| `--decide` | No | `false` | Write a brain ADR summarising the stack health snapshot |
| `--dry-run` | No | `false` | — |
| `--json` | No | `false` | — |
| `--alert` | No | `false` | Warn when a repo drops or falls below min-score |
| `--threshold` | No | `10` | Point drop that triggers an alert |

## `mq-agent stack truth-export`

Write the mq-stack truth snapshot (contract + release gates) to mqobsidian. Primary name: `stack truth-export`. `stack export` is kept as a backwards-compatible alias — both run the same export. Pass ``--rebuild-views`` to refresh agent views at the end of the workflow (opt-in — see docs/AGENT_VIEW_CONTRACT.md phase C).

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--output`, `-o` | No | `""` | Output path (default: dated note under mqobsidian/memory/stack-truth/) |
| `--dry-run` | No | `false` | — |
| `--json` | No | `false` | — |
| `--rebuild-views` | No | `false` | Also rebuild agent views after export (opt-in, off by default) |

## `mq-agent swarm`

Multi-agent swarm workflows.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent swarm audit`](#mq-agent-swarm-audit) | Full read-only repo health check: audit + signal + docs. |
| [`mq-agent swarm list`](#mq-agent-swarm-list) | List available swarm configurations and their agents. |
| [`mq-agent swarm plan`](#mq-agent-swarm-plan) | Show which agents would run — no execution, no API calls. |
| [`mq-agent swarm release-check`](#mq-agent-swarm-release-check) | Release readiness swarm: CI + audit + release validation. |
| [`mq-agent swarm run`](#mq-agent-swarm-run) | Run a named swarm config against a repo path. |

## `mq-agent swarm audit`

Full read-only repo health check: audit + signal + docs.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | No | `.` | Repo path |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--dry-run` | No | `false` | — |
| `--json` | No | `false` | — |

## `mq-agent swarm list`

List available swarm configurations and their agents.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent swarm plan`

Show which agents would run — no execution, no API calls.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `CONFIG` | Yes | — | Swarm config name (audit, release-check, ci) |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent swarm release-check`

Release readiness swarm: CI + audit + release validation.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | No | `.` | Repo path |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--dry-run` | No | `true` | — |
| `--approve` | No | `false` | — |
| `--json` | No | `false` | — |

## `mq-agent swarm run`

Run a named swarm config against a repo path.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `CONFIG` | Yes | — | Swarm config name (audit, release-check, ci) |
| `PATH` | No | `.` | Repo path |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--dry-run` | No | `false` | — |
| `--approve` | No | `false` | Allow write-capable agents |
| `--json` | No | `false` | — |

## `mq-agent task`

Run declarative YAML task workflows.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent task list`](#mq-agent-task-list) | List available task definitions. |
| [`mq-agent task run`](#mq-agent-task-run) | Run a declarative YAML task workflow. |

## `mq-agent task list`

List available task definitions.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent task run`

Run a declarative YAML task workflow.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `NAME` | Yes | — | Task name or path to YAML file |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--dry-run` | No | `false` | — |
| `--json` | No | `false` | — |

## `mq-agent tools`

List registered tools. Use --describe `<name>` for details, --mcp to include MCP tools.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--describe` | No | — | Show details for a specific tool |
| `--mcp` | No | `false` | Include discovered MCP tools |
| `--json` | No | `false` | — |

## `mq-agent tui`

Launch the Textual TUI dashboard.

## `mq-agent workflow`

Bounded multi-step workflow templates (list/show/plan). Read-only in v1.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent workflow cancel`](#mq-agent-workflow-cancel) | Cancel a run. |
| [`mq-agent workflow list`](#mq-agent-workflow-list) | List the available workflow templates. |
| [`mq-agent workflow plan`](#mq-agent-workflow-plan) | Build and print a validated plan for REPO. Does not run or persist it. |
| [`mq-agent workflow resume`](#mq-agent-workflow-resume) | Resume a paused or failed run from where it stopped. |
| [`mq-agent workflow run`](#mq-agent-workflow-run) | Instantiate, persist and execute a workflow against REPO (read-only). |
| [`mq-agent workflow show`](#mq-agent-workflow-show) | Show a template's raw definition as JSON. |
| [`mq-agent workflow status`](#mq-agent-workflow-status) | Show a run's current state. Does not execute anything. |

## `mq-agent workflow cancel`

Cancel a run.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `RUN_ID` | Yes | — | Run id to cancel. |

## `mq-agent workflow list`

List the available workflow templates.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | Emit JSON. |

## `mq-agent workflow plan`

Build and print a validated plan for REPO. Does not run or persist it.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `TEMPLATE` | Yes | — | Template name, e.g. repo-preflight. |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--repo` | Yes | — | Target repository path. |

## `mq-agent workflow resume`

Resume a paused or failed run from where it stopped.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `RUN_ID` | Yes | — | Run id of a paused or failed run. |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |
| `--yes`, `-y` | No | `false` | Approve the plan without prompting. |

## `mq-agent workflow run`

Instantiate, persist and execute a workflow against REPO (read-only).

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `TEMPLATE` | Yes | — | Template name, e.g. repo-preflight. |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--repo` | Yes | — | Target repository path. |
| `--json` | No | `false` | Emit the summary as JSON. |
| `--yes`, `-y` | No | `false` | Approve the plan without prompting. |

## `mq-agent workflow show`

Show a template's raw definition as JSON.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `TEMPLATE` | Yes | — | Template name, e.g. repo-preflight. |

## `mq-agent workflow status`

Show a run's current state. Does not execute anything.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `RUN_ID` | Yes | — | Run id, e.g. run_20260626_001. |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |
