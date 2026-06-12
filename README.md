# mq-agent

[![Tests](https://github.com/MCamner/mq-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/MCamner/mq-agent/actions)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-v1.18.0-brightgreen)](https://mcamner.github.io/mq-agent/)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://mcamner.github.io/mq-agent/)

Terminal-native AI agent orchestrator for the mq ecosystem.

## 30 second demo

```bash
mq-agent doctor                    # check environment
mq-agent score .                   # README + publish score (no API key)
mq-agent audit . --dry-run         # repo audit plan
mq-agent release-check --dry-run   # release readiness plan
```

```mermaid
flowchart TD
    A[mqlaunch] --> B[mq-agent]
    B --> C[mq-hal\nreasoning]
    B --> D[mq-mcp\ntool layer]
    B --> E[repo-signal\nrepo intel]
    B --> F[Planner]
    B --> G[Executor]
    B --> H[Verifier]
    B --> I[Memory]
    B --> J[Safety]
```

Screenshots/gallery: the GitHub Pages demo page shows the current command
surface and release proof.

## Why

Most AI coding tools either wrap a model around shell commands or hide execution behind a chat UI.

mq-agent is different: it treats agent work as a controlled terminal workflow with explicit planning, tool routing, verification, memory and safety gates. Every action is traceable, every operation is gated, and the model never runs unsupervised.

## Use cases

mq-agent is useful when you want to:

- audit a repository before publishing
- generate a release readiness plan with explicit approval gates
- score README and publish quality without an API key
- inspect and fix CI failures with AI-generated steps
- run safe terminal workflows where the model cannot act without permission
- combine repo-signal, mq-mcp and mq-hal into one local agent workflow

## What it is

Not an AI wrapper script. An actual orchestrator with:

| Layer        | Responsibility               |
|--------------|------------------------------|
| **Planner**  | Decomposes goals into steps  |
| **Executor** | Runs steps through tools     |
| **Verifier** | Checks each result with AI   |
| **Memory**   | Session + persistent state   |
| **Safety**   | Enforces operation modes     |

## Quick start

```bash
# Install
uv pip install -e ".[dev,signal]"

# Check environment
mq-agent doctor

# Score a repo (no API key needed)
mq-agent score .

# Full AI-backed repo assessment
export OPENAI_API_KEY=sk-...
mq-agent signal .

# Read-only audit
mq-agent audit .
```

## Development flow

`main` is protected. Use a branch and pull request for all development and
release-prep changes:

```bash
git switch -c chore/release-vX.Y.Z
mq-agent release-check --dry-run
git push -u origin chore/release-vX.Y.Z
gh pr create --base main --head chore/release-vX.Y.Z
```

Merge the PR only after CI is green. Create release tags from the merged
`main` commit.

## Install

### Local development

```bash
uv pip install -e ".[dev,signal]"
```

### From GitHub

```bash
pipx install git+https://github.com/MCamner/mq-agent.git
```

### PyPI (planned)

```bash
pipx install mq-agent   # coming soon
```

Requires `OPENAI_API_KEY` for AI commands. `score`, `doctor`, `repo-summary` and `tools` work without it.

## Demo

```text
$ mq-agent score .
╭──────────────────────── README Score ─────────────────────────╮
│ README score: 100/100  [██████████]                           │
│ ✓ title  ✓ install  ✓ usage  ✓ examples  ✓ badges            │
│ ✓ license  ✓ roadmap  ✓ contributing  (none missing)          │
╰───────────────────────────────────────────────────────────────╯
╭──────────────────── Publish Checklist ────────────────────────╮
│ Publish checklist: 16/16  [PASS]                              │
│ Repo looks publish-ready from the static checklist.           │
╰───────────────────────────────────────────────────────────────╯
```

See [docs/DEMO.md](docs/DEMO.md) for the full end-to-end walkthrough.

## CLI

```bash
mq-agent audit .                   # Read-only repo audit
mq-agent release-plan              # Show release plan
mq-agent release-check             # Validate release readiness (suggest mode)
mq-agent release-check --approve   # Execute checks
mq-agent repo-summary .            # Quick repo overview
mq-agent run "pytest" --approve    # Safe shell execution
mq-agent fix-ci                    # Diagnose CI failures
mq-agent doctor                    # Check environment
mq-agent tools                     # List registered tools
mq-agent tools --mcp               # Include discovered MCP tools
mq-agent tools --describe <name>   # Show tool metadata and safety class
mq-agent mcp status                # Check mq-mcp reachability and tool counts
mq-agent mcp tools                 # List all MCP tools with safety classes
mq-agent run-tool <tool>           # Run an MCP tool through safety gates
mq-agent review file <path>        # Review one file through mq-mcp
mq-agent review diff               # Review current diff through mq-mcp
mq-agent review repo [path]        # Review repo through mq-mcp
mq-agent review file <path> --fast # Prefer Class A tools (mq-mcp routes)
mq-agent review diff --fast
mq-agent review file <path> --architecture-image docs/arch.png
mq-agent learn status              # Check mq-mcp learn system
mq-agent learn search <query>      # Search learned review patterns
mq-agent learn explain <pattern>   # Fetch pattern explanation
mq-agent dashboard                  # Operator snapshot: stack, brain, Ollama, contracts
mq-agent stack loop                 # Controlled autonomous stack loop preview
mq-agent tui                       # Launch Textual dashboard

# All commands support --dry-run and --json
mq-agent audit . --dry-run
mq-agent run-tool read_repo_file --arg path=README.md --dry-run
```

Review commands are pass-through orchestration for mq-mcp review tools. They
route to `review_file`, `review_diff`, `review_repo`, or supported risk review
tools through `MCPBridge`; mq-agent does not implement local review logic,
severity scoring, architecture reasoning, or risk classification.

## Safety modes

```text
read-only   → only read tools allowed
suggest     → plan shown, nothing executed (default for most commands)
execute     → runs after safety check (requires --approve for destructive ops)
dangerous   → no restrictions (requires explicit flag)
```

## Architecture

```text
mq_agent/
├── core/
│   ├── state.py          # AgentState, PlanStep, SafetyMode, StepStatus
│   ├── planner.py        # OpenAI-backed plan generation
│   ├── executor.py       # Tool routing + safety enforcement
│   ├── verification.py   # OpenAI-backed result verification
│   ├── memory.py         # Session + persistent memory
│   └── safety.py         # Safety gate (mode enforcement)
├── tools/
│   ├── git_tools.py      # git_status, git_log, git_diff, git_branch, git_remote
│   ├── shell_tools.py    # run_command (blocked pattern list)
│   ├── repo_tools.py     # repo_summary, list_files, read_file, find_files
│   ├── signal_tools.py   # repo_scan, repo_readme_score, repo_publish_checklist, repo_analyze
│   └── mcp_bridge.py     # HTTP bridge to mq-mcp
├── agents/
│   ├── audit_agent.py    # Repo audit (read-only)
│   ├── release_agent.py  # Release validation
│   ├── ci_agent.py       # CI failure diagnosis
│   ├── docs_agent.py     # Documentation audit
│   └── signal_agent.py   # repo-signal static scan + AI improvement plan
├── tui/
│   └── app.py            # Textual dashboard
├── prompts/
│   ├── planner.md        # System prompt for Planner
│   └── verifier.md       # System prompt for Verifier
└── tasks/
    ├── release.yaml      # Declarative release task
    ├── audit.yaml        # Declarative audit task
    └── fix_ci.yaml       # Declarative CI fix task
```

## Proof

- 408+ tests pass — `uv run pytest -v` — no OpenAI calls required
- `mq-agent score .` — 100/100 README, 16/16 publish checklist [PASS]
- `mq-agent doctor` — all required checks pass
- `mq-agent audit . --dry-run` — safe, read-only plan generation
- `mq-agent signal . --dry-run` — repo-signal assessment without execution
- Safety modes documented and enforced — dangerous patterns blocked at tool level
- `--dry-run` and `--json` supported on all commands

```bash
uv run pytest tests/ -v
```

## Docs

- [Command reference](docs/COMMANDS.md)
- [Command surface](docs/COMMAND_SURFACE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [MQ control plane](docs/MQ_CONTROL_PLANE.md)
- [Memory engine](docs/MEMORY_ENGINE.md)
- [Safety contract](docs/SAFETY_CONTRACT.md)
- [Ollama-backed learn extraction](docs/LEARN_OLLAMA.md)
- [mq ecosystem](docs/MQ_ECOSYSTEM.md)
- [Skills](SKILLS.md)
- [Examples](docs/EXAMPLES.md)
- [Safety](docs/SAFETY.md)
- [Roadmap](docs/ROADMAP.md)
- [Release checklist](docs/RELEASE_CHECKLIST.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## v1.18.0 status

- [x] `mq-agent memory ingest` — local mqobsidian Markdown index
- [x] `mq-agent memory query` / `memory search-vault` — read-only vault search
- [x] `mq-agent memory summarize` — section summary across truth, reviews, learn, releases, architecture and decisions
- [x] `mq-agent memory link` — read-only link candidates between notes
- [x] `docs/MEMORY_ENGINE.md`
- [x] Write-backed links deferred to a later explicit approval flow

## v1.19.0 status

- [x] `mq-agent dashboard` — read-only operator snapshot for stack health, contracts, mqobsidian truth freshness and Ollama profile status
- [x] `mq-agent tui` — starts with the same operator snapshot before command execution

## v1.17.0 status

- [x] `mq-agent models` — first-class Ollama model runtime command group
- [x] `mq-agent models list/current/switch/bench`
- [x] Model profiles persisted in `~/.mq-agent/models.json`
- [x] `mq-agent stack run` surfaces the active model profile in the Ollama check
- [x] v1.17.0 release docs/status sync
- [x] Full suite and stack gates before PR

## v1.16.0 status

- [x] `mq-agent stack run` — one runtime gate for repo-signal, mq-mcp, Ollama, brain export rendering and release readiness
- [x] `mq-agent run --stack` — canonical root alias for the stack runtime pipeline
- [x] Runtime output supports `--json` and `--markdown`
- [x] `docs/MQ_CONTROL_PLANE.md` — system map for signal, review, learn, memory and release
- [x] v1.17.0 set as next focus: Ollama runtime

## v1.15.0 status

- [x] `mq-agent stack cockpit` — one merged view of the whole stack: version, branch, contract, release gate, brain-export freshness, next action per repo
- [x] Flag contract enforced across the command surface: `--dry-run` never writes, `--json` machine-readable, `--brain` respects `--dry-run`, `--approve` required for write flows (locked by `tests/test_flag_contract.py`)
- [x] `mq-agent brain structure` — standard mqobsidian export structure: check, `--init --approve`, legacy detection
- [x] `mq-agent stack brain-gate` — pre-release checklist: contract-check + release-check + truth-export dry-run + vault structure + review→brain write path
- [x] Fixed: `signal --brain --dry-run` no longer writes to the brain
- [x] `docs/STACK_COCKPIT.md`, `docs/VAULT_STRUCTURE.md`, `docs/BRAIN_GATE.md` — reference docs
- [x] 56 new tests (511 total)

## v1.14.0 status

- [x] `mq-agent stack release --repo <name>` — orchestrated single-repo release pipeline
- [x] Dry-run by default; `--execute` applies; `--bump patch|minor|major` or explicit `--version`
- [x] Release-check pre-gate, version bump, contract sync, changelog from release-notes draft
- [x] Release commit, tag, push, closing `truth-export` to mqobsidian
- [x] Abort on first failed step with pre-commit rollback — no half-released repos
- [x] `docs/STACK_RELEASE.md` — reference doc
- [x] 27 new tests (455 total)

## v1.13.0 status

- [x] `mq-agent stack truth-export` — durable stack truth note (contract + release gates) to mqobsidian
- [x] `mq-agent stack export` kept as backwards-compatible alias
- [x] Default note path: `~/mqobsidian/memory/stack-truth/YYYY-MM-DD-mq-stack-truth.md`
- [x] `stack contract-check --ci` / `stack release-check --ci` — CI mode with SKIPPED for missing repos
- [x] `mq-stack-gate.yml` split: fast `--ci` gate on PRs, full multi-repo gate on main/nightly
- [x] `docs/STACK_TRUTH_EXPORT.md` — reference doc
- [x] 25 new tests (439 total)

## v1.12.0 status

- [x] `.github/workflows/mq-stack-gate.yml` — CI workflow for MQ stack gates
- [x] CI checks out active MQ stack repos and links them to expected `~/...` paths
- [x] `mq-agent stack contract-check --json` runs on pull requests and pushes to `main`
- [x] `mq-agent stack release-check --json` runs on pull requests and pushes to `main`
- [x] Stack drift and release blockers now fail CI before merge

## v1.11.0 status

- [x] `mq-agent stack contract-check` — validates `.mq/repo-contract.json` across all stack repos
- [x] `mq-agent stack contract-check --json` — machine-readable output
- [x] `_contract_entry()` helper with READY / REVIEW / DRIFT / BLOCKED status model
- [x] `schemas/mq_stack_repo_contract.schema.json` — JSON Schema for contract manifests
- [x] `.mq/repo-contract.json` deployed to all 8 MQ stack repos
- [x] `docs/STACK_CONTRACT_GATE.md` — reference doc
- [x] 19 new tests (408 total)

## v1.10.0 status

- [x] `mq-agent stack release-notes` — draft notes from git commits since last tag, per repo
- [x] `mq-agent stack release-notes --repo <name>` — single repo filter
- [x] `mq-agent stack release-notes --json` — machine-readable output
- [x] `docs/STACK_RELEASE_NOTES.md` — reference doc
- [x] 13 new tests (389 total)

## v1.9.0 status

- [x] `mq-agent stack report` — score, trend, alert, readiness per repo in one table
- [x] `mq-agent stack report --json` — machine-readable
- [x] `mq-agent stack release-check` — local release gate across all stack repos (exit 1 on blocker)
- [x] `mq-agent stack release-check --json` — GO/NO-GO with per-repo detail
- [x] `docs/STACK_REPORT.md` — reference with example output and workflow
- [x] 15 new tests (376 total)

## v1.8.0 status

- [x] `mq-agent stack alert` — exits 1 when a repo drops ≥ threshold or falls below min-score
- [x] `mq-agent stack sweep --alert` — inline alert check at the end of a sweep
- [x] `--threshold N` / `--min-score N` — configurable thresholds
- [x] `--json` — machine-readable alert list, CI-friendly exit codes
- [x] `docs/STACK_ALERT.md` — reference with CI integration examples
- [x] 18 new tests (361 total)

## v1.7.0 status

- [x] `mq-agent stack sweep` appends every run to `~/.mq-agent/sweep-history.jsonl`
- [x] `mq-agent stack history` — tabular trend view across last N sweeps
- [x] `mq-agent stack history --diff` — delta table between last two sweeps
- [x] `mq-agent stack history --json` / `--limit N` — scripting and filtering
- [x] `docs/STACK_HISTORY.md` — reference with example output and JSON scripting
- [x] 13 new tests (343 total)

## v1.6.0 status

- [x] `mq-agent stack sweep` — loop repo-signal over all mq-stack repos in one pass
- [x] `mq-agent stack sweep --brain` — write a brain note per repo to mqobsidian
- [x] `mq-agent stack sweep --decide` — consolidated health ADR via `brain_record_decision`
- [x] `mq-agent stack sweep --dry-run` — preview without writes
- [x] `mq-agent stack sweep --json` — machine-readable summary table
- [x] mqlaunch agent menu item 18 — Stack health sweep
- [x] `docs/STACK_HEALTH.md` — multi-repo sweep reference with example output

## v1.5.0 status

- [x] End-to-end demo flow: `mq-agent signal . --brain` → `mq-agent review repo . --brain` → `mq-agent release-check --dry-run`
- [x] `mqlaunch/commands/demo-flow.sh` — standalone chain script
- [x] mqlaunch agent menu item 17 — Demo flow (full stack)
- [x] `docs/DEMO.md` rewritten as canonical v1.5.0 reference

## v1.4.0 status

- [x] `mq-image-analyze` MCP endpoint registered for visual perception tools
- [x] `mq-agent run-tool observe_architecture` routes through mq-image-analyze
- [x] `mq-agent run-tool image_ocr` routes through mq-image-analyze
- [x] `mq-agent review file|diff|repo --architecture-image <path>` adds `visual_architecture_observation.v1` context
- [x] Image-analysis tools remain delegated; mq-agent does not implement perception locally

## v1.3.0 status

- [x] Architecture-memory context surfaced automatically after review findings (`list_architecture_decisions`)
- [x] `--fast` flag on all review commands — mq-mcp routes to Class A tools
- [x] `mq-agent learn status/search/explain` — read-only access to mq-mcp learned patterns
- [x] Optional Ollama-backed learn extraction documented as an mq-mcp-owned policy
- [x] `MultiMCPBridge._call_optional_tool()` — silent None when tool not available
- [x] 292 tests pass — `uv run pytest -v` — no OpenAI calls required

## v1.1.0 status

- [x] `mq-agent review file/diff/repo` — pass-through review orchestration via mq-mcp
- [x] `--security`, `--architecture`, `--risk` flags forwarded to mq-mcp review contracts
- [x] `--dry-run` on all review commands — shows planned mq-mcp call without executing
- [x] `validate_orchestration_contract` in `mq-agent doctor`
- [x] 252 tests pass — `uv run pytest -v` — no OpenAI calls required for test suite

## v1.0.0 status

- [x] Stable orchestration platform — all contracts locked, full docs, complete examples
- [x] `cli/render.py` + `core/diagnostics.py` — orchestration logic extracted from main.py
- [x] `Planner` wired to `MqAgentConfig.effective_model()` — config-driven model selection
- [x] 237 tests pass — `uv run pytest -v` — no OpenAI calls required for test suite

## v0.9.0 status

- [x] 14-test orchestration contract suite locking PlanStep, StepResult,
      AgentManifest, AgentState, tool registry, and run_task delegation
- [x] `mq_agent/config.py` — MqAgentConfig dataclass with load/save
      and MQ_AGENT_MODEL env override
- [x] Docstrings clarifying PlanStep vs StepResult boundary and
      SwarmRunner's role as a separate runtime
- [x] 218 tests pass — `uv run pytest -v` — no OpenAI calls required

## v0.8.0 status

- [x] Controlled task runner workflows — `mq-agent task list/run`
- [x] Browser-safe URL inspection and release verification
- [x] Multi-agent swarm planning and dry-run workflows
- [x] Orchestration stabilization checkpoint — `docs/ARCHITECTURE.md`
- [x] Contract tests for no-API command behavior and registry stability
- [x] 211 tests pass — `uv run pytest -v` — no OpenAI calls required

## v0.5.1 status

- [x] Planner (OpenAI gpt-4o, structured JSON output)
- [x] Executor (tool registry, dry-run, safety gate)
- [x] Verifier (OpenAI gpt-4o-mini, per-step verification)
- [x] Memory (session + persistent JSON)
- [x] Safety (read-only / suggest / execute / dangerous)
- [x] Git tools, shell tools, repo tools
- [x] MCP bridge (mq-mcp over HTTP) with safety classification
- [x] Audit agent, Release agent, CI agent, Docs agent, Signal agent
- [x] Textual TUI, JSON output, `--dry-run` on all commands
- [x] `mq-agent doctor` — full environment check
- [x] `mq-agent mcp status` / `mq-agent mcp tools` — MCP inspection
- [x] `mq-agent tools --describe <name>` — tool metadata and safety class
- [x] `mq-agent run-tool <tool>` — MCP tool through safety gates
- [x] MCP safety classes: read-only / write-capable / subprocess / dangerous / unknown
- [x] mqlaunch bridge — 12-item agent menu + 6 direct prompt commands
- [x] `scripts/smoke-mqlaunch.sh` — verifies `mqlaunch agent ...` reaches mq-agent
- [x] `docs/MQLAUNCH_INTEGRATION.md` — bridge architecture and usage
- [x] `docs/COMMAND_SURFACE.md` — single source of truth for command counts
- [x] 94 tests pass — `uv run pytest -v` — no OpenAI calls required
- [x] Semantic repository memory — `mq-agent memory status / build / refresh`
- [x] `mq-agent memory doctor` — diagnose memory environment with actionable fixes
- [x] `mq-agent memory status --json` / `mq-agent memory doctor --json` — machine-readable output

## Semantic repository memory

mq-agent v0.5.0 adds semantic repository memory via repo-signal.

```bash
mq-agent memory status                # check vector store and repo-signal
mq-agent memory doctor                # diagnose environment with actionable fixes
mq-agent memory build .               # preview upload (dry-run default)
mq-agent memory refresh . --approve   # upload when ready
mq-agent memory status --json         # machine-readable output
```

Memory upload is explicit and gated. mq-agent never uploads silently.

### Verified output

```text
$ mq-agent memory status
╭────────────────────────────── Semantic Memory ───────────────────────────────╮
│ status:       missing-vector-store                                           │
│ vector store: (not set — export OPENAI_VECTOR_STORE_ID)                      │
│ repo-signal:  available                                                      │
│ repo:         /Users/mansys/mq-agent                                         │
╰──────────────────────────────────────────────────────────────────────────────╯

$ mq-agent memory build .
[dry-run] Would run: repo-signal semantic-upload
Add --no-dry-run to execute, or use memory refresh --approve.

$ mq-agent memory doctor
╭──────────────────────── Memory Doctor ───────────────────────────╮
│ ✗ OPENAI_VECTOR_STORE_ID: (not set)                              │
│   fix: export OPENAI_VECTOR_STORE_ID=vs_...                      │
│ ✓ repo-signal: available                                         │
│ ✓ repo path: /Users/mansys/mq-agent                              │
╰──────────────────────────────────────────────────────────────────╯
```

See [docs/SEMANTIC_MEMORY.md](docs/SEMANTIC_MEMORY.md).

## mqlaunch integration

`mq-agent` is fully wired into `mqlaunch` as both a direct command surface and
an interactive menu.

```bash
mqlaunch agent
mqlaunch agent score .
mqlaunch agent audit .
mqlaunch agent doctor
mqlaunch agent release-check --dry-run
mqlaunch agent mcp-status
mqlaunch agent mcp-tools
```

See [docs/COMMAND_SURFACE.md](docs/COMMAND_SURFACE.md) for the canonical
command surface and [docs/MQLAUNCH_INTEGRATION.md](docs/MQLAUNCH_INTEGRATION.md)
for bridge details.

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md) for the current roadmap.

Current direction:

- send stack gate results to the brain (`--brain`)
- keep mq-agent orchestration-only
- keep review logic, learn extraction, memory and risk reasoning in mq-mcp
- improve mq ecosystem integrations without adding hidden autonomy

## Notes

Do not commit API keys, local secrets, or private environment files.
