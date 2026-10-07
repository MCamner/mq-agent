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
| [`mq-agent execution`](#mq-agent-execution) | group | Inspect observed execution outcomes. |
| [`mq-agent feedback`](#mq-agent-feedback) | group | Run and inspect evidence-grounded feedback experiments. |
| [`mq-agent fix-ci`](#mq-agent-fix-ci) | command | Diagnose CI failures and suggest fixes. |
| [`mq-agent learn`](#mq-agent-learn) | group | Learn commands — extraction, storage and promotion of review patterns. |
| [`mq-agent mcp`](#mq-agent-mcp) | group | Inspect and manage the local mq-mcp tool server. |
| [`mq-agent memory`](#mq-agent-memory) | group | Semantic repository memory commands. |
| [`mq-agent models`](#mq-agent-models) | group | Ollama model runtime commands. |
| [`mq-agent notebook`](#mq-agent-notebook) | group | Build local source packs for optional synthesis providers. |
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
| [`mq-agent skills`](#mq-agent-skills) | group | Inspect and select local skills for a task. |
| [`mq-agent stack`](#mq-agent-stack) | group | mq-stack repo inventory, status, and Obsidian export. |
| [`mq-agent state`](#mq-agent-state) | group | Inventory, snapshot, verify and restore allowlisted MQ runtime state. |
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
| [`mq-agent context feedback`](#mq-agent-context-feedback) | Record one `feedback-signal.v1` pack-usage event in the vault's local log. Phase 11c: mqobsidian owns the vocabulary and the promotion/downgrade policy; this emits the signal. Records land in the gitignored `feedback/` surface and are never committed. |
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

## `mq-agent context feedback`

Record one `feedback-signal.v1` pack-usage event in the vault's local log. Phase 11c: mqobsidian owns the vocabulary and the promotion/downgrade policy; this emits the signal. Records land in the gitignored `feedback/` surface and are never committed.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `TASK` | Yes | — | The task the pack was built for |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--outcome` | No | `""` | sufficient or insufficient — did the pack carry the task |
| `--repo` | No | `""` | Primary repo for the task |
| `--judgment` | No | — | Per-block verdict as `block:judgment[:reason]` where judgment is useful\|noise\|missing\|stale (repeatable) |
| `--notes` | No | `""` | Free-text note kept local |
| `--vault` | No | `""` | mqobsidian vault path (default: $MQ_OBSIDIAN_DIR or ~/mqobsidian) |
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
| `--codegraph` | No | `auto` | CodeGraph hint: auto, on, off, or policy (feedback-controlled) |
| `--task-class` | No | `repo-review` | Task class used for feedback-controlled context policy |
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
| `--route` | No | `local-shadow` | Applied route for the docs review: local-shadow (local model) or deterministic-local (extraction, no inference) |

## `mq-agent doctor`

Check mq-agent environment and dependencies.

## `mq-agent execution`

Inspect observed execution outcomes.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent execution compare`](#mq-agent-execution-compare) | Compare two observed routes without selecting a winner. |
| [`mq-agent execution report`](#mq-agent-execution-report) | Report execution metrics without mixing in shadow outcomes. |

## `mq-agent execution compare`

Compare two observed routes without selecting a winner.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--task-class` | Yes | — | Task class to compare |
| `--left` | Yes | — | First route |
| `--right` | Yes | — | Second route |
| `--source` | No | — | JSON or JSONL execution outcome source |
| `--since` | No | — | Time window: 7d, 30d, or 90d |
| `--json` | No | `false` | — |

## `mq-agent execution report`

Report execution metrics without mixing in shadow outcomes.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--source` | No | — | JSON or JSONL execution outcome source |
| `--since` | No | — | Time window: 7d, 30d, or 90d |
| `--task-class` | No | — | Limit report to one task class |
| `--json` | No | `false` | — |

## `mq-agent feedback`

Run and inspect evidence-grounded feedback experiments.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent feedback activate`](#mq-agent-feedback-activate) | Activate one task-class strategy after approval and a passing Canary v2 result. |
| [`mq-agent feedback activation-readiness`](#mq-agent-feedback-activation-readiness) | Check evidence readiness for human activation approval; never activates. |
| [`mq-agent feedback approve`](#mq-agent-feedback-approve) | Issue an expiring approval receipt bound to exact candidate evidence. |
| [`mq-agent feedback canary-check`](#mq-agent-feedback-canary-check) | Validate one legacy v1.31 comparison; read-only and not activation-authorizing. |
| [`mq-agent feedback canary-plan`](#mq-agent-feedback-canary-plan) | Create one immutable Canary v2 plan; no experiment is executed. |
| [`mq-agent feedback canary-run`](#mq-agent-feedback-canary-run) | Execute one bounded Canary v2 plan and append one immutable RESULT. |
| [`mq-agent feedback canary-status`](#mq-agent-feedback-canary-status) | Show authoritative append-only PLAN/RESULT state for one canary. |
| [`mq-agent feedback candidate`](#mq-agent-feedback-candidate) | Show one candidate with its immutable comparison evidence. |
| [`mq-agent feedback candidate-handoff`](#mq-agent-feedback-candidate-handoff) | Submit an approved memory candidate to mqobsidian's review inbox. |
| [`mq-agent feedback candidate-state`](#mq-agent-feedback-candidate-state) | Append a human review state; never activates a policy. |
| [`mq-agent feedback candidates`](#mq-agent-feedback-candidates) | List effective reviewable improvement candidates. |
| [`mq-agent feedback compare`](#mq-agent-feedback-compare) | Read the latest comparison or derive one from explicit relevance evidence. |
| [`mq-agent feedback inspect`](#mq-agent-feedback-inspect) | Explain one immutable experiment, comparison and candidate chain. |
| [`mq-agent feedback policy`](#mq-agent-feedback-policy) | Show the effective feedback-controlled task-class policy. |
| [`mq-agent feedback post-activation-check`](#mq-agent-feedback-post-activation-check) | Surface material regressions against the measured shadow baseline. |
| [`mq-agent feedback purge`](#mq-agent-feedback-purge) | Delete local runtime feedback evidence; production behavior is unchanged. |
| [`mq-agent feedback recent`](#mq-agent-feedback-recent) | List retained feedback experiments newest first. |
| [`mq-agent feedback report`](#mq-agent-feedback-report) | Aggregate feedback evidence without recomputing a verdict. |
| [`mq-agent feedback rollback`](#mq-agent-feedback-rollback) | Roll back one exact currently-active Policy Registry v2 activation. |
| [`mq-agent feedback run`](#mq-agent-feedback-run) | Run one zero-effect active-versus-shadow repo-review experiment. |
| [`mq-agent feedback status`](#mq-agent-feedback-status) | Show feedback storage health and experiment coverage. |

## `mq-agent feedback activate`

Activate one task-class strategy after approval and a passing Canary v2 result.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `CANDIDATE_ID` | Yes | — | Feedback candidate identifier |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--approval-id` | Yes | — | — |
| `--canary-id` | Yes | — | Passing Canary v2 identifier |
| `--reason` | Yes | — | — |
| `--approve` | No | `false` | Required: change one task-class policy |
| `--json` | No | `false` | — |

## `mq-agent feedback activation-readiness`

Check evidence readiness for human activation approval; never activates.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `CANDIDATE_ID` | Yes | — | Feedback candidate identifier |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent feedback approve`

Issue an expiring approval receipt bound to exact candidate evidence.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `CANDIDATE_ID` | Yes | — | Feedback candidate identifier |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--reason` | Yes | — | Human approval reason |
| `--expires-hours` | No | `24` | — |
| `--approve` | No | `false` | Required: issue approval receipt |
| `--json` | No | `false` | — |

## `mq-agent feedback canary-check`

Validate one legacy v1.31 comparison; read-only and not activation-authorizing.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `CANDIDATE_ID` | Yes | — | Feedback candidate identifier |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--approval-id` | Yes | — | — |
| `--comparison-id` | Yes | — | Post-approval canary comparison |
| `--json` | No | `false` | — |

## `mq-agent feedback canary-plan`

Create one immutable Canary v2 plan; no experiment is executed.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `CANDIDATE_ID` | Yes | — | Approved feedback candidate |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--approval-id` | Yes | — | — |
| `--executions` | No | `3` | — |
| `--min-executions` | No | `3` | — |
| `--max-duration-seconds` | No | `300` | — |
| `--max-failure-rate` | No | `0.0` | — |
| `--json` | No | `false` | — |

## `mq-agent feedback canary-run`

Execute one bounded Canary v2 plan and append one immutable RESULT.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `CANARY_ID` | Yes | — | Canary v2 identifier |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--task` | Yes | — | Task used only for zero-effect context selection |
| `--fixture` | Yes | — | Deterministic relevance fixture JSON |
| `--repo` | No | `.` | Clean Git repository to evaluate |
| `--vault` | No | — | mqobsidian vault override |
| `--timeout-ms` | No | `2000` | — |
| `--max-context-bytes` | No | `65536` | — |
| `--max-sources` | No | `64` | — |
| `--json` | No | `false` | — |

## `mq-agent feedback canary-status`

Show authoritative append-only PLAN/RESULT state for one canary.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `CANARY_ID` | Yes | — | Canary v2 identifier |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent feedback candidate`

Show one candidate with its immutable comparison evidence.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `CANDIDATE_ID` | Yes | — | Feedback candidate identifier |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent feedback candidate-handoff`

Submit an approved memory candidate to mqobsidian's review inbox.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `CANDIDATE_ID` | Yes | — | Approved memory candidate |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--confidence` | Yes | — | — |
| `--json` | No | `false` | — |

## `mq-agent feedback candidate-state`

Append a human review state; never activates a policy.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `CANDIDATE_ID` | Yes | — | Feedback candidate identifier |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--state` | Yes | — | deferred, rejected, or approved-for-handoff |
| `--reason` | Yes | — | Human review reason |
| `--json` | No | `false` | — |

## `mq-agent feedback candidates`

List effective reviewable improvement candidates.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent feedback compare`

Read the latest comparison or derive one from explicit relevance evidence.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `FEEDBACK_RUN_ID` | Yes | — | Feedback run identifier |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--fixture` | No | — | Explicit deterministic relevance fixture JSON |
| `--atlas-evaluation` | No | — | Optional Atlas Core advisory evaluation bound to observed evidence refs |
| `--json` | No | `false` | — |

## `mq-agent feedback inspect`

Explain one immutable experiment, comparison and candidate chain.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `FEEDBACK_RUN_ID` | Yes | — | Feedback run identifier |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent feedback policy`

Show the effective feedback-controlled task-class policy.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `TASK_CLASS` | No | `repo-review` | Task class |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent feedback post-activation-check`

Surface material regressions against the measured shadow baseline.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `TASK_CLASS` | Yes | — | Activated task class |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--comparison-id` | Yes | — | — |
| `--json` | No | `false` | — |

## `mq-agent feedback purge`

Delete local runtime feedback evidence; production behavior is unchanged.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--approve` | No | `false` | Required: delete local runtime feedback evidence |
| `--json` | No | `false` | — |

## `mq-agent feedback recent`

List retained feedback experiments newest first.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--limit` | No | `20` | Newest records to return (1-200) |
| `--json` | No | `false` | — |

## `mq-agent feedback report`

Aggregate feedback evidence without recomputing a verdict.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--task-class` | No | — | Limit report to one task class |
| `--since` | No | — | Positive day window, e.g. 30d |
| `--json` | No | `false` | — |

## `mq-agent feedback rollback`

Roll back one exact currently-active Policy Registry v2 activation.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `ACTIVATION_ID` | Yes | — | Exact activation policy event id |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--reason` | Yes | — | — |
| `--approve` | No | `false` | Required: append rollback event |
| `--json` | No | `false` | — |

## `mq-agent feedback run`

Run one zero-effect active-versus-shadow repo-review experiment.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--task` | Yes | — | Task used only in-memory for context selection |
| `--repo` | No | `.` | Clean Git repository to evaluate |
| `--task-class` | No | `repo-review` | Feedback task class |
| `--vault` | No | — | mqobsidian vault override |
| `--timeout-ms` | No | `2000` | Hard per-strategy collection deadline |
| `--max-context-bytes` | No | `65536` | — |
| `--max-sources` | No | `64` | — |
| `--json` | No | `false` | — |

## `mq-agent feedback status`

Show feedback storage health and experiment coverage.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

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
| [`mq-agent memory build`](#mq-agent-memory-build) | Preview semantic repo memory upload. Non-dry-run uses refresh safety. |
| [`mq-agent memory doctor`](#mq-agent-memory-doctor) | Diagnose semantic memory environment. |
| [`mq-agent memory emit-cochange`](#mq-agent-memory-emit-cochange) | Emit one co-change memory-observation.v1 from Bridget/CG-2 evidence. mq-agent is the producer; Bridget/CG-2 is the evidence source. Writes nothing when no co-change cluster clears the gate. mqobsidian scores and promotes. |
| [`mq-agent memory hybrid-shadow`](#mq-agent-memory-hybrid-shadow) | Compare active semantic memory with hybrid retrieval in zero-effect shadow mode. |
| [`mq-agent memory inbox-cochange`](#mq-agent-memory-inbox-cochange) | Operator-triggered co-change intake: emit → score → writeback → status. Runs the autonomous learning loop end-to-end for one file, but only when you ask (not auto-after-workflow). mq-agent orchestrates; Bridget/CG-2 is evidence source; mqobsidian owns scoring/writeback/status (invoked via its own local-only CLI). |
| [`mq-agent memory ingest`](#mq-agent-memory-ingest) | Scan mqobsidian memory notes into a local read-only index. |
| [`mq-agent memory learn-writeback`](#mq-agent-memory-learn-writeback) | Materialise durable agent-readable memory for PROMOTED memories. Dry-run by default. inbox-cochange runs this as stage 4 of intake; this is the same verb standalone, for promotions that landed another way. mqobsidian decides what counts as promoted — candidate and observed memories are never written. |
| [`mq-agent memory link`](#mq-agent-memory-link) | Infer read-only link candidates between mqobsidian notes. |
| [`mq-agent memory promote-from-review`](#mq-agent-memory-promote-from-review) | Approve a held promotion-review memory → promote it (co-change never auto-promotes). Appends a promotion-event + directive snapshot via mqobsidian's CLI. Dry-run by default. |
| [`mq-agent memory query`](#mq-agent-memory-query) | Search mqobsidian memory notes. Alias: search-vault. |
| [`mq-agent memory refresh`](#mq-agent-memory-refresh) | Refresh semantic repo memory. Requires --approve; cleanup is explicit. |
| [`mq-agent memory resolve-supersede`](#mq-agent-memory-resolve-supersede) | Accept or reject a deep-conflict supersede proposal (exactly one of --accept/--reject). |
| [`mq-agent memory review-status`](#mq-agent-memory-review-status) | Show the mqobsidian scoring review state: tier tally + held review queues (read-only). Delegates to mqobsidian's local-only CLI; mq-agent stays the orchestrator so mqlaunch never reaches mqobsidian directly. |
| [`mq-agent memory search`](#mq-agent-memory-search) | Search mq-mcp semantic memory. Read-only. Requires mq-mcp v1.4.0+. |
| [`mq-agent memory search-vault`](#mq-agent-memory-search-vault) | Search mqobsidian memory notes. Alias: search-vault. |
| [`mq-agent memory session-handoff`](#mq-agent-memory-session-handoff) | Submit typed session facts as memory-observation.v1 for normal review. |
| [`mq-agent memory status`](#mq-agent-memory-status) | Check semantic repository memory availability. |
| [`mq-agent memory store`](#mq-agent-memory-store) | Store an item in mq-mcp semantic memory. Class C write tool — requires --approve. |
| [`mq-agent memory summarize`](#mq-agent-memory-summarize) | Summarize mqobsidian memory by section. |

## `mq-agent memory build`

Preview semantic repo memory upload. Non-dry-run uses refresh safety.

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

## `mq-agent memory hybrid-shadow`

Compare active semantic memory with hybrid retrieval in zero-effect shadow mode.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `QUERY` | Yes | — | Retrieval query |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--catalog` | No | `""` | Optional notebook-corpus-index.v1 JSON |
| `--semantic-index` | No | `""` | Optional local notebook semantic index JSON |
| `--semantic-model` | No | `nomic-embed-text` | Local Ollama embedding model |
| `--top-k` | No | `10` | — |
| `--json` | No | `false` | — |

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

Refresh semantic repo memory. Requires --approve; cleanup is explicit.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `PATH` | No | `.` | Repo path |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--approve` | No | `false` | Allow upload |
| `--cleanup-stale` | No | `false` | Detach stale retrieval generations after verified upload |

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

## `mq-agent memory session-handoff`

Submit typed session facts as memory-observation.v1 for normal review.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--session-id` | Yes | — | — |
| `--task-class` | Yes | — | — |
| `--repo` | Yes | — | — |
| `--outcome` | Yes | — | — |
| `--decision` | No | — | Verified decision (repeatable) |
| `--artifact` | No | — | Evidence/artifact reference (repeatable) |
| `--correction` | No | — | Explicit operator correction (repeatable) |
| `--confidence` | No | `0.7` | — |
| `--vault` | No | `""` | mqobsidian vault override |
| `--approve` | No | `false` | Required: append a memory observation candidate |
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

## `mq-agent notebook`

Build local source packs for optional synthesis providers.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent notebook atlas`](#mq-agent-notebook-atlas) | P5: emit an Atlas-safe claim/evidence bundle from NotebookLM sources. |
| [`mq-agent notebook build`](#mq-agent-notebook-build) | Build P0 and optionally P1, then record the P3 baseline. |
| [`mq-agent notebook catalog`](#mq-agent-notebook-catalog) | Inspect one local Drive-corpus catalog without reading file bodies. |
| [`mq-agent notebook evidence`](#mq-agent-notebook-evidence) | P4: retrieve bounded, provenance-bearing evidence for mq-agent. |
| [`mq-agent notebook gaps`](#mq-agent-notebook-gaps) | Find repeated, unsupported, derived-only, and stale research questions. |
| [`mq-agent notebook inventory`](#mq-agent-notebook-inventory) | Inventory the configured Drive corpus using read-only metadata APIs. |
| [`mq-agent notebook pack`](#mq-agent-notebook-pack) | Preview or build one local, provenance-bearing notebook source pack. |
| [`mq-agent notebook questions`](#mq-agent-notebook-questions) | Extract recurring questions from interaction history without treating it as evidence. |
| [`mq-agent notebook research`](#mq-agent-notebook-research) | Synthesize D5 evidence across notebooks with deterministic provenance gates. |
| [`mq-agent notebook retrieve`](#mq-agent-notebook-retrieve) | Fetch a bounded provenance-bearing evidence bundle from D4 candidates. |
| [`mq-agent notebook search`](#mq-agent-notebook-search) | Search local corpus metadata plus optional provider text-match metadata. |
| [`mq-agent notebook semantic-build`](#mq-agent-notebook-semantic-build) | Build a disposable local D8 semantic experiment index. |
| [`mq-agent notebook semantic-eval`](#mq-agent-notebook-semantic-eval) | Compare D8 semantic retrieval with D4 on the exact frozen query set. |
| [`mq-agent notebook semantic-search`](#mq-agent-notebook-semantic-search) | Search the disposable D8 semantic index without changing evidence roles. |
| [`mq-agent notebook show`](#mq-agent-notebook-show) | Show one catalog notebook or item by exact identity. |
| [`mq-agent notebook status`](#mq-agent-notebook-status) | Show P0-P5 NotebookLM pipeline readiness without provider calls. |
| [`mq-agent notebook sync`](#mq-agent-notebook-sync) | P3: diff the current catalog and optionally update only changed vectors. |

## `mq-agent notebook atlas`

P5: emit an Atlas-safe claim/evidence bundle from NotebookLM sources.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `CLAIM` | Yes | — | Document claim Atlas should verify |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--catalog` | No | `.mq/notebook-corpus/catalog.json` | — |
| `--max-files` | No | `4` | — |
| `--max-bytes-per-file` | No | `1048576` | P5 full-capture limit per source |
| `--output` | No | `""` | Optional JSON evidence bundle path |
| `--workspace` | No | `""` | Optional immutable Atlas evidence workspace directory |
| `--access-token-env` | No | `MQ_NOTEBOOK_DRIVE_ACCESS_TOKEN` | — |
| `--json` | No | `false` | — |

## `mq-agent notebook build`

Build P0 and optionally P1, then record the P3 baseline.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--d3-input` | No | `.mq/notebook-corpus/d3-input.json` | Normalized Drive inventory projection |
| `--catalog` | No | `.mq/notebook-corpus/catalog.json` | Canonical local corpus catalog |
| `--checkpoint` | No | `.mq/notebook-corpus/catalog.checkpoint.json` | P0 catalog build checkpoint |
| `--manifest` | No | `""` | Optional reconciled NotebookLM manifest integrity overlay |
| `--semantic` | No | `false` | Also build the local semantic index (P1) |
| `--semantic-index` | No | `.mq/notebook-corpus/semantic-index.json` | Local semantic index output |
| `--sync-state` | No | `.mq/notebook-corpus/sync-state.json` | Local incremental sync state |
| `--embed-model` | No | `nomic-embed-text` | Ollama embedding model |
| `--ollama-host` | No | `""` | Optional Ollama host override |
| `--access-token-env` | No | `MQ_NOTEBOOK_DRIVE_ACCESS_TOKEN` | Environment variable containing a Drive OAuth access token |
| `--json` | No | `false` | — |

## `mq-agent notebook catalog`

Inspect one local Drive-corpus catalog without reading file bodies.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--catalog` | No | `""` | Path to local notebook-corpus-index.v1 JSON |
| `--json` | No | `false` | — |

## `mq-agent notebook evidence`

P4: retrieve bounded, provenance-bearing evidence for mq-agent.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `QUERY` | Yes | — | Claim/question to ground in NotebookLM corpus |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--catalog` | No | `.mq/notebook-corpus/catalog.json` | — |
| `--max-files` | No | `4` | — |
| `--access-token-env` | No | `MQ_NOTEBOOK_DRIVE_ACCESS_TOKEN` | — |
| `--json` | No | `false` | — |

## `mq-agent notebook gaps`

Find repeated, unsupported, derived-only, and stale research questions.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--catalog` | No | `""` | Path to local notebook-corpus-index.v1 JSON |
| `--text-hits` | No | `""` | Optional provider text-hit metadata JSON for source/derived matching |
| `--max-files` | No | `20` | Maximum interaction files to inspect |
| `--max-bytes-per-file` | No | `65536` | — |
| `--max-total-bytes` | No | `524288` | — |
| `--top-k` | No | `20` | Maximum metadata/text candidates per question |
| `--stale-after-days` | No | `365` | Age threshold for a stale source theme |
| `--access-token-env` | No | `MQ_NOTEBOOK_DRIVE_ACCESS_TOKEN` | Environment variable containing a Drive OAuth access token |
| `--json` | No | `false` | — |

## `mq-agent notebook inventory`

Inventory the configured Drive corpus using read-only metadata APIs.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--root-id` | No | `""` | Configured Drive corpus root item ID |
| `--checkpoint` | No | `.mq/notebook-corpus/inventory.json` | Local inventory checkpoint JSON |
| `--changes` | No | `false` | Use Drive change feed; requires a completed checkpoint |
| `--max-pages` | No | — | Stop after N provider pages and keep partial state |
| `--access-token-env` | No | `MQ_NOTEBOOK_DRIVE_ACCESS_TOKEN` | Environment variable containing a Drive OAuth access token |
| `--d3-input` | No | `""` | Optional path for normalized D3 input; requires current inventory |
| `--snapshot-at` | No | `""` | Archive snapshot timestamp used only with --d3-input |
| `--exclude-root-folder-id` | No | — | Top-level folder ID to exclude from notebook candidates (repeatable) |
| `--json` | No | `false` | — |

## `mq-agent notebook pack`

Preview or build one local, provenance-bearing notebook source pack.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `NOTEBOOK` | Yes | — | Logical notebook ID |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--vault` | No | `""` | mqobsidian vault path (default: $MQ_OBSIDIAN_DIR or ~/mqobsidian) |
| `--output-root` | No | `""` | Local output root (default: `<vault>`/.notebooklm) |
| `--write` | No | `false` | Materialize the local pack; preview is the default |
| `--replace` | No | `false` | Replace an existing owned pack; requires --write |
| `--json` | No | `false` | — |

## `mq-agent notebook questions`

Extract recurring questions from interaction history without treating it as evidence.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--catalog` | No | `""` | Path to local notebook-corpus-index.v1 JSON |
| `--max-files` | No | `20` | Maximum interaction files to inspect |
| `--max-bytes-per-file` | No | `65536` | — |
| `--max-total-bytes` | No | `524288` | — |
| `--access-token-env` | No | `MQ_NOTEBOOK_DRIVE_ACCESS_TOKEN` | Environment variable containing a Drive OAuth access token |
| `--json` | No | `false` | — |

## `mq-agent notebook research`

Synthesize D5 evidence across notebooks with deterministic provenance gates.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `QUESTION` | Yes | — | Cross-notebook research question |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--catalog` | No | `""` | Path to local notebook-corpus-index.v1 JSON |
| `--text-hits` | No | `""` | Optional provider text-hit metadata JSON |
| `--scope` | No | `archive` | archive or live-runtime |
| `--top-k` | No | `20` | — |
| `--max-files` | No | `8` | — |
| `--max-bytes-per-file` | No | `65536` | — |
| `--max-total-bytes` | No | `524288` | — |
| `--excerpt-chars` | No | `4000` | — |
| `--access-token-env` | No | `MQ_NOTEBOOK_DRIVE_ACCESS_TOKEN` | Environment variable containing a Drive OAuth access token |
| `--model` | No | `""` | Ollama model; default is current mq-agent model profile |
| `--timeout` | No | `60` | Ollama synthesis timeout in seconds |
| `--review-candidate-out` | No | `""` | Optional local JSON review-candidate path; never promotes memory |
| `--json` | No | `false` | — |

## `mq-agent notebook retrieve`

Fetch a bounded provenance-bearing evidence bundle from D4 candidates.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `QUERY` | Yes | — | Archive retrieval question |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--catalog` | No | `""` | Path to local notebook-corpus-index.v1 JSON |
| `--text-hits` | No | `""` | Optional provider text-hit metadata JSON |
| `--scope` | No | `archive` | archive or live-runtime |
| `--max-files` | No | `4` | Maximum selected corpus items |
| `--max-bytes-per-file` | No | `65536` | — |
| `--max-total-bytes` | No | `262144` | — |
| `--excerpt-chars` | No | `4000` | — |
| `--access-token-env` | No | `MQ_NOTEBOOK_DRIVE_ACCESS_TOKEN` | Environment variable containing a Drive OAuth access token |
| `--json` | No | `false` | — |

## `mq-agent notebook search`

Search local corpus metadata plus optional provider text-match metadata.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `QUERY` | Yes | — | Lexical corpus query |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--catalog` | No | `""` | Path to local notebook-corpus-index.v1 JSON |
| `--text-hits` | No | `""` | Optional provider text-hit metadata JSON |
| `--top-k` | No | `10` | Maximum returned candidates |
| `--connector-calls` | No | `0` | Adapter calls represented by supplied text hits |
| `--json` | No | `false` | — |

## `mq-agent notebook semantic-build`

Build a disposable local D8 semantic experiment index.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--catalog` | No | `""` | Path to local notebook-corpus-index.v1 JSON |
| `--output` | No | `.mq/notebook-corpus/semantic-index.json` | Disposable local semantic index JSON |
| `--model` | No | `nomic-embed-text` | Local Ollama embedding model |
| `--max-files` | No | `50` | — |
| `--max-bytes-per-file` | No | `65536` | — |
| `--max-total-bytes` | No | `1048576` | — |
| `--chunk-chars` | No | `2000` | — |
| `--overlap-chars` | No | `200` | — |
| `--access-token-env` | No | `MQ_NOTEBOOK_DRIVE_ACCESS_TOKEN` | — |
| `--json` | No | `false` | — |

## `mq-agent notebook semantic-eval`

Compare D8 semantic retrieval with D4 on the exact frozen query set.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--catalog` | No | `""` | Path to local notebook-corpus-index.v1 JSON |
| `--index` | No | `.mq/notebook-corpus/semantic-index.json` | Disposable semantic index JSON |
| `--expected` | No | `""` | JSON map of frozen query -> expected Drive item ids |
| `--model` | No | `nomic-embed-text` | Local Ollama embedding model |
| `--top-k` | No | `5` | — |
| `--json` | No | `false` | — |

## `mq-agent notebook semantic-search`

Search the disposable D8 semantic index without changing evidence roles.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `QUERY` | Yes | — | Semantic experiment query |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--index` | No | `.mq/notebook-corpus/semantic-index.json` | Disposable semantic index JSON |
| `--model` | No | `nomic-embed-text` | Local Ollama embedding model |
| `--top-k` | No | `10` | — |
| `--json` | No | `false` | — |

## `mq-agent notebook show`

Show one catalog notebook or item by exact identity.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `IDENTIFIER` | Yes | — | Logical or Drive notebook/item identity |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--catalog` | No | `""` | Path to local notebook-corpus-index.v1 JSON |
| `--json` | No | `false` | — |

## `mq-agent notebook status`

Show P0-P5 NotebookLM pipeline readiness without provider calls.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--catalog` | No | `.mq/notebook-corpus/catalog.json` | — |
| `--semantic-index` | No | `.mq/notebook-corpus/semantic-index.json` | — |
| `--sync-state` | No | `.mq/notebook-corpus/sync-state.json` | — |
| `--json` | No | `false` | — |

## `mq-agent notebook sync`

P3: diff the current catalog and optionally update only changed vectors.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--catalog` | No | `.mq/notebook-corpus/catalog.json` | — |
| `--d3-input` | No | `""` | Optional refreshed D3 projection to materialize before diffing |
| `--checkpoint` | No | `.mq/notebook-corpus/catalog.checkpoint.json` | — |
| `--manifest` | No | `""` | Optional reconciled manifest used with --d3-input |
| `--sync-state` | No | `.mq/notebook-corpus/sync-state.json` | — |
| `--semantic` | No | `false` | Incrementally update semantic vectors for NEW/CHANGED items |
| `--semantic-index` | No | `.mq/notebook-corpus/semantic-index.json` | — |
| `--embed-model` | No | `nomic-embed-text` | — |
| `--ollama-host` | No | `""` | — |
| `--access-token-env` | No | `MQ_NOTEBOOK_DRIVE_ACCESS_TOKEN` | — |
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
| [`mq-agent review perception`](#mq-agent-review-perception) | Produce and inspect perception.v1 through mq-image-analyze. This command is orchestration only: mq-image-analyze owns visual extraction. mq-agent preserves the returned risk signals/limitations and does not invent a second vision or review engine. |
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
| `--receipt` | No | `false` | Require and save mq-mcp exact-code review receipt |
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
| `--receipt` | No | `false` | Require and save mq-mcp exact-code review receipt |
| `--repo` | No | — | External repo path the file lives in (within mq-mcp allowlist) |
| `--json` | No | `false` | — |
| `--dry-run` | No | `false` | Show what would be called, no execution |

## `mq-agent review perception`

Produce and inspect perception.v1 through mq-image-analyze. This command is orchestration only: mq-image-analyze owns visual extraction. mq-agent preserves the returned risk signals/limitations and does not invent a second vision or review engine.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `IMAGE_PATH` | Yes | — | Image/screenshot/diagram path |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--producer` | No | `ui` | ui, architecture, or ocr |
| `--source-type` | No | — | screenshot, diagram, ui, terminal, or browser |
| `--json` | No | `false` | — |
| `--dry-run` | No | `false` | — |

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
| `--receipt` | No | `false` | Require and save mq-mcp exact-code review receipt |
| `--json` | No | `false` | — |
| `--dry-run` | No | `false` | Show what would be called, no execution |

## `mq-agent route`

Inspect advisory local-first model routing.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent route divergence`](#mq-agent-route-divergence) | Compare applied routes within one era. Reports, never promotes. |
| [`mq-agent route evidence-review`](#mq-agent-route-evidence-review) | Review one task class without promoting it or changing routing policy. |
| [`mq-agent route history`](#mq-agent-route-history) | List individual routing outcomes newest first, read-only. |
| [`mq-agent route inspect`](#mq-agent-route-inspect) | Recommend a route without model calls or writes. |
| [`mq-agent route readiness`](#mq-agent-route-readiness) | Show distance to evidence thresholds without changing routing. |
| [`mq-agent route report`](#mq-agent-route-report) | Aggregate validated routing outcomes from a read-only source. |
| [`mq-agent route shadow`](#mq-agent-route-shadow) | Run and verify an advisory Ollama candidate without accepting it. |

## `mq-agent route divergence`

Compare applied routes within one era. Reports, never promotes.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--source` | No | — | JSON or JSONL outcome source |
| `--era` | No | — | Analysis era; defaults to the current one |
| `--task-class` | No | — | Limit to one routing task class |
| `--json` | No | `false` | — |

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

## `mq-agent route readiness`

Show distance to evidence thresholds without changing routing.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--source` | No | — | JSON or JSONL execution outcome source |
| `--json` | No | `false` | — |

## `mq-agent route report`

Aggregate validated routing outcomes from a read-only source.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--source` | No | — | JSON or JSONL outcome source |
| `--since` | No | — | Time window: 7d, 30d, or 90d |
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
| `--timeout` | No | `600` | Ollama timeout in seconds |
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

## `mq-agent skills`

Inspect and select local skills for a task.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent skills inventory`](#mq-agent-skills-inventory) | Show profiles, support and actual discovery separately. |
| [`mq-agent skills profile`](#mq-agent-skills-profile) | Show vocabulary matches without selecting or running skills. |
| [`mq-agent skills route`](#mq-agent-skills-route) | Select skills deterministically; 0 complete/empty, 1 partial, 2 invalid. |

## `mq-agent skills inventory`

Show profiles, support and actual discovery separately.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--repo` | No | `.` | Repository name or directory |
| `--vault` | No | — | mqobsidian contracts; defaults to MQ_OBSIDIAN_DIR or ~/mqobsidian |
| `--json` | No | `false` | — |

## `mq-agent skills profile`

Show vocabulary matches without selecting or running skills.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `TASK` | Yes | — | — |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--repo` | No | `.` | Repository name or directory |
| `--target` | No | `codex` | codex, claude, or both |
| `--vault` | No | — | mqobsidian contracts; defaults to MQ_OBSIDIAN_DIR or ~/mqobsidian |
| `--json` | No | `false` | — |

## `mq-agent skills route`

Select skills deterministically; 0 complete/empty, 1 partial, 2 invalid.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `TASK` | Yes | — | — |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--repo` | No | `.` | Repository name or directory |
| `--target` | No | `codex` | codex, claude, or both |
| `--vault` | No | — | mqobsidian contracts; defaults to MQ_OBSIDIAN_DIR or ~/mqobsidian |
| `--json` | No | `false` | — |
| `--explain` | No | `false` | — |

## `mq-agent stack`

mq-stack repo inventory, status, and Obsidian export.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent stack alert`](#mq-agent-stack-alert) | Warn when a repo dropped >= threshold points or is below min-score since the last sweep. Exits 0 when no alerts, exits 1 when alerts are found (CI-friendly). |
| [`mq-agent stack brain-gate`](#mq-agent-stack-brain-gate) | Brain release gate: contract-check + release-check + truth-export dry-run + vault structure + the review→brain write path, all green before a release. Read-only; exit 1 on NO-GO. |
| [`mq-agent stack cockpit`](#mq-agent-stack-cockpit) | One-table stack cockpit: repo, version, branch, dirty, contract, release gate, unreleased work, brain-export freshness and next action. Read-only — combines stack status, contract-check, release-check and the latest mqobsidian stack-truth note into a single view. Later the input to mq-hal. |
| [`mq-agent stack compatibility`](#mq-agent-stack-compatibility) | Assess dependency compatibility across MQ repositories (read-only). A repo can be green while the stack holds a latent incompatibility: an unbounded range, or a lockfile masking what a fresh install would pick. This reads declared and locked versions with provenance and never modifies dependencies, lockfiles or working trees. --fresh-resolve answers what a new installation would select today. It resolves outside every working tree, never reads or writes a lockfile, and reports an unreachable registry as UNAVAILABLE rather than incompatibility. Exit codes: 0 PASS or WARN, 1 WARN under --strict, 2 FAIL, 3 UNAVAILABLE, 130 interrupted. |
| [`mq-agent stack contract-check`](#mq-agent-stack-contract-check) | Validate that every mq-stack repo declares a contract manifest. Reads .mq/repo-contract.json per repo and checks VERSION sync. No API key required. Exits 1 if any repo is BLOCKED or DRIFT. With --ci, repos missing from the workspace are SKIPPED instead of BLOCKED — the CI checkout itself is still fully validated. |
| [`mq-agent stack export`](#mq-agent-stack-export) | Write the mq-stack truth snapshot (contract + release gates) to mqobsidian. Primary name: `stack truth-export`. `stack export` is kept as a backwards-compatible alias — both run the same export. Pass ``--rebuild-views`` to refresh agent views at the end of the workflow (opt-in — see docs/AGENT_VIEW_CONTRACT.md phase C). |
| [`mq-agent stack history`](#mq-agent-stack-history) | Show repo health scores from past stack sweeps. |
| [`mq-agent stack loop`](#mq-agent-stack-loop) | Plan or execute one v1.20 controlled autonomous stack loop. Dry-run by default. `--execute --approve` runs one allowlisted action with command-specific rollback behaviour. |
| [`mq-agent stack protection-check`](#mq-agent-stack-protection-check) | Compare declared branch protection against GitHub and a real pull request. Read-only: every GitHub call is a GET. Applying protection stays a separate, explicit operation, because a PUT replaces the whole protection object and silently drops anything the payload leaves out. Three layers are compared — the contract in mq_agent/data/branch_protection.yaml, GitHub's protection, and the contexts the most recent pull request actually reported. Needs `gh` and network. Exits 1 on any drift. |
| [`mq-agent stack provenance`](#mq-agent-stack-provenance) | Show which code this runtime is, and whether its layers agree. Compares the source checkout, the installed runtime and the release identity. Read-only, local and network-free: `origin/main` is the ref this machine already has and is never fetched, so an unverified remote is the normal state rather than staleness. Always exits 0. Provenance reports facts; whether a difference blocks a release or a write of production evidence belongs to the release cockpit and to runtime_guard. |
| [`mq-agent stack release`](#mq-agent-stack-release) | Orchestrated single-repo release: gate, bump, changelog, tag, push, truth-export. Dry-run by default — shows the plan without touching the repo. With --execute the plan is applied step by step; any failed step aborts the run and pre-commit file edits are rolled back. Exits 1 on NO-GO or on a failed step. Ends with a stack truth-export so the release lands in mqobsidian memory. With --all, plans a release for every stack repo at once (dry-run by default): each repo is reported as ready, blocked, or up-to-date. Exits 1 if any repo is blocked. Release a ready repo with --repo `<name>` --execute. With --all --preflight, runs the read-only multi-repo release preflight: the strict fail-fast refusal surface (dirty, off-main, unpushed, tag exists, version mismatch, and each repo's release-check.sh). Never mutates and never executes; exits 1 if any repo is blocked. Pull-request repos stop in AWAITING_MERGE without directly releasing other repos. Finalize a verified merged release PR explicitly with --finalize-pr, --repo, --version and --approve. |
| [`mq-agent stack release-check`](#mq-agent-stack-release-check) | Run release-readiness checks across all mq-stack repos. Checks per repo: VERSION file, CHANGELOG entry, clean working tree, on main/master branch. No API key required. Exits 1 on any blocker. With --ci, sibling repos missing from the workspace are skipped instead of blocking — only repos that are present (e.g. the CI checkout) gate. |
| [`mq-agent stack release-notes`](#mq-agent-stack-release-notes) | Draft release notes from git commits since the last tag, per repo. Reads git log since last tag for each mq-stack repo. No API key required. Always exits 0 (informational). |
| [`mq-agent stack report`](#mq-agent-stack-report) | Consolidated stack health view: score, trend, alert and readiness per repo. Reads sweep history for scores and trend; no API key required. |
| [`mq-agent stack run`](#mq-agent-stack-run) | Run the v1.16 stack runtime gate. Checks repo-signal, mq-mcp, Ollama, brain export rendering and release readiness in one operator-facing pass. Read-only by default; `--brain` writes the truth export only when `--approve` is also supplied. |
| [`mq-agent stack skills-check`](#mq-agent-stack-skills-check) | Validate skill consistency across every mq-stack repo. Runs each repo's scripts/check-skills.sh (frontmatter, skill cross-references, referenced paths, SKILLS.md sync). No API key required. Exits 1 if any repo is DRIFT (skills inconsistent) or BLOCKED. With --ci, repos missing from the workspace are SKIPPED. |
| [`mq-agent stack status`](#mq-agent-stack-status) | Show exact-head verification state and evidence age for all mq-stack repos. |
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

Assess dependency compatibility across MQ repositories (read-only). A repo can be green while the stack holds a latent incompatibility: an unbounded range, or a lockfile masking what a fresh install would pick. This reads declared and locked versions with provenance and never modifies dependencies, lockfiles or working trees. --fresh-resolve answers what a new installation would select today. It resolves outside every working tree, never reads or writes a lockfile, and reports an unreachable registry as UNAVAILABLE rather than incompatibility. Exit codes: 0 PASS or WARN, 1 WARN under --strict, 2 FAIL, 3 UNAVAILABLE, 130 interrupted.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |
| `--all` | No | `false` | Inventory the whole stack instead of the MCP slice |
| `--fresh-resolve` | No | `false` | Also resolve declared ranges in a temporary directory and probe critical imports (needs uv and network) |
| `--strict` | No | `false` | Exit 1 on WARN instead of 0 |

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

## `mq-agent stack protection-check`

Compare declared branch protection against GitHub and a real pull request. Read-only: every GitHub call is a GET. Applying protection stays a separate, explicit operation, because a PUT replaces the whole protection object and silently drops anything the payload leaves out. Three layers are compared — the contract in mq_agent/data/branch_protection.yaml, GitHub's protection, and the contexts the most recent pull request actually reported. Needs `gh` and network. Exits 1 on any drift.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |
| `--repo` | No | `""` | Check a single repo from the contract |

## `mq-agent stack provenance`

Show which code this runtime is, and whether its layers agree. Compares the source checkout, the installed runtime and the release identity. Read-only, local and network-free: `origin/main` is the ref this machine already has and is never fetched, so an unverified remote is the normal state rather than staleness. Always exits 0. Provenance reports facts; whether a difference blocks a release or a write of production evidence belongs to the release cockpit and to runtime_guard.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |
| `--refresh` | No | `false` | Ask the remote what it holds; the only step that uses the network |

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

Show exact-head verification state and evidence age for all mq-stack repos.

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

## `mq-agent state`

Inventory, snapshot, verify and restore allowlisted MQ runtime state.

### Subcommands

| Subcommand | Description |
|---|---|
| [`mq-agent state inventory`](#mq-agent-state-inventory) | Inventory allowlisted, sanitized local MQ runtime state. |
| [`mq-agent state restore`](#mq-agent-state-restore) | Restore manifest-declared files only; never delete unrelated current state. |
| [`mq-agent state snapshot`](#mq-agent-state-snapshot) | Copy allowlisted runtime state into a portable content-hashed snapshot. |
| [`mq-agent state verify`](#mq-agent-state-verify) | Verify manifest, hashes, paths and unexpected files without writing state. |

## `mq-agent state inventory`

Inventory allowlisted, sanitized local MQ runtime state.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

## `mq-agent state restore`

Restore manifest-declared files only; never delete unrelated current state.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `SNAPSHOT_DIR` | Yes | — | Verified snapshot directory |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--approve` | No | `false` | Required: restore allowlisted runtime state |
| `--json` | No | `false` | — |

## `mq-agent state snapshot`

Copy allowlisted runtime state into a portable content-hashed snapshot.

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--output` | Yes | — | Empty/new snapshot directory |
| `--json` | No | `false` | — |

## `mq-agent state verify`

Verify manifest, hashes, paths and unexpected files without writing state.

### Arguments

| Argument | Required | Default | Description |
|---|---:|---|---|
| `SNAPSHOT_DIR` | Yes | — | Snapshot directory |

### Options

| Option | Required | Default | Description |
|---|---:|---|---|
| `--json` | No | `false` | — |

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
