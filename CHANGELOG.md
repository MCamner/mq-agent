# Changelog

All notable changes to mq-agent are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [v0.8.0] — 2026-05-24

### Added

- `mq-agent swarm list` — list available swarm configs with agents and safety classes
- `mq-agent swarm plan <config>` — show participating agents; no API calls needed
- `mq-agent swarm run <config> [path]` — execute a named swarm, unified report
- `mq-agent swarm audit [path]` — shorthand: audit + signal + docs swarm
- `mq-agent swarm release-check [path]` — shorthand: CI + audit + release swarm
- `mq_agent/core/swarm.py` — `AgentManifest`, `SwarmConfig`, `AgentResult`, `SwarmResult`, `SwarmRunner`
- `mq_agent/agents/swarm_registry.py` — built-in swarm configs: `audit`, `release-check`, `ci`
- Each `AgentManifest` declares: purpose, safety_class, allowed_tools, requires_approve, output_contract, failure_behavior
- Dry-run mode requires no API key and skips all agent execution
- `--approve` gate for write-capable agents (`release` manifest)
- `tasks/swarm_audit.yaml` — declarative swarm audit task workflow
- `tests/test_swarm.py` — 29 tests covering manifests, configs, runner, registry, CLI
- 190 tests total

---

## [v0.7.0] — 2026-05-24

### Added

- `mq-agent browser inspect <url>` — fetch and parse URL metadata: title, description, headings, links, word count
- `mq-agent browser summarize <url>` — plain-text content summary from a URL
- `mq-agent browser verify-release <url>` — verify release page fields; `--tag <v>` checks expected version tag
- `mq_agent/tools/browser_tools.py` — `fetch_url`, `inspect_url`, `summarize_url`, `verify_release_url`
- `_HTMLExtractor` — stdlib-only HTML parser (title, description, h1/h2, links, text)
- URL safety gate: blocks `file://`, `ftp://`, `data:`, `javascript:` schemes
- Browser tools registered in `TOOL_REGISTRY` — usable in task YAML workflows
- `tasks/browser_verify.yaml` — declarative task for release page verification
- `tests/test_browser.py` — 27 tests covering URL safety, HTML parsing, inspect/summarize/verify, and CLI commands
- 161 tests total

---

## [v0.6.0] — 2026-05-24

### Added

- `mq-agent task list` — list available YAML task workflow files
- `mq-agent task list --json` — machine-readable task list with name, description, step count
- `mq-agent task run <name>` — execute a declarative YAML workflow via the tool registry
- `mq-agent task run <name> --dry-run` — preview steps without execution (default: False)
- `mq-agent task run <name> --json` — machine-readable step results
- `mq_agent/core/task_runner.py` — `TaskStep`, `StepResult`, `Task`, `load_task`, `run_task`, `find_task_files`
- Task lookup by filename stem OR internal YAML `name:` field — both `audit` and `repo-audit` resolve correctly
- `tests/test_task_runner.py` — 18 tests covering `load_task`, `run_task`, `find_task_files` and CLI commands

---

## [v0.5.2] — 2026-05-24

### Added

- `mq-agent mcp start` — start mq-mcp server in background (SSE transport, PID file managed)
- `mq-agent mcp stop` — stop the background mq-mcp server
- `mq_agent/mcp/manager.py` — PID-file-based process lifecycle: `start()`, `stop()`, `is_running()`, `read_pid()`
- `mq-agent mcp status` now shows process state (running/not running) from PID file alongside HTTP reachability
- `mq-agent mcp status --json` includes `process_running` and `pid` fields
- `mq-agent mcp start/stop --json` — machine-readable output
- 14 new tests in `tests/test_mcp.py` covering manager module and CLI commands

### Changed

- `mq-agent mcp status` — not-running state now shows "Start with: mq-agent mcp start"
- `MCPBridge.not_reachable_message()` — now suggests `mq-agent mcp start` instead of raw uv command

---

## [v0.5.1] — 2026-05-24

### Added

- `mq-agent memory doctor` — diagnose environment with per-item status and actionable fixes
- `mq-agent memory doctor --json` — machine-readable diagnostics
- `mq-agent memory status --json` — machine-readable status output
- `DoctorReport` and `DiagnosticItem` dataclasses in `mq_agent/memory/semantic.py`
- `doctor()` function in `mq_agent/memory/semantic.py`
- `tests/test_memory_cli.py` — 18 CLI-level tests covering dry-run default, approval gate, JSON output and doctor diagnostics
- Example output for `memory doctor` in `docs/SEMANTIC_MEMORY.md` and README

### Changed

- README semantic memory section expanded with verified output and `memory doctor` example
- `docs/COMMAND_SURFACE.md` updated with `memory doctor` and `--json` variants

---

## [v0.5.0] — 2026-05-24

### Added

- `mq-agent memory status` — check vector store ID and repo-signal availability
- `mq-agent memory build .` — dry-run semantic upload preview (safe default)
- `mq-agent memory refresh . --approve` — upload semantic memory (gate required)
- `mq_agent/memory/semantic.py` — `SemanticMemoryStatus`, `get_vector_store_id()`, `status()`, `build()`
- `docs/SEMANTIC_MEMORY.md` — commands, environment, safety model and failure states
- `scripts/smoke-memory.sh` — smoke test for memory status and build dry-run

### Safety

- `memory build` defaults to `--dry-run`; no upload without `--no-dry-run`
- `memory refresh` requires `--approve`; exits 1 without it
- Missing vector store and missing repo-signal reported explicitly, never silent

### Changed

- README updated to v0.5.0 with semantic memory section
- Roadmap updated: v0.5.0 semantic memory marked complete; autonomous loop/browser moved to Later

---

## [v0.4.1] — 2026-05-23

### Added

- `docs/COMMAND_SURFACE.md` — canonical command-count reference for mq-agent, MCP commands, mqlaunch menu items, direct prompt commands and smoke-test coverage
- Docs consistency checks guard mqlaunch command counts and require all six direct prompt commands to be documented
- `mq-agent docs-audit .` — CLI command exposing `DocsAgent` (implementation existed but had no registered entrypoint)
- `MQ_AGENT_MODEL` env var — overrides the planner model (default: `gpt-4o`)
- `MQ_AGENT_VERIFIER_MODEL` env var — overrides the verifier model (default: `gpt-4o-mini`)
- `memory` field on `AgentState` — `Memory` wired into the agent lifecycle; `AuditAgent` loads prior context and saves summary after each run

### Removed

- `mq_agent/cli.py` — dead parallel click-based CLI (never registered as entrypoint, `click` was an undeclared dependency)
- `mq_agent/memory/` — empty directory left over from a refactor

### Fixed

- Safety gate `_is_destructive()` matched keywords in step descriptions ("format output", "remove duplicates") — now checks `run_command` args only
- `find_files()` parameter renamed `suffix` → `pattern` to match AI planner output; default updated from `".py"` to `"*.py"`
- TUI version label hardcoded to `v0.1.0` — now reads `__version__` from package metadata
- TUI command list was stale (7 entries, pre-v0.3.0) — updated to all 12 current commands
- TUI `subprocess.run()` blocked the Textual event loop — replaced with `asyncio.create_subprocess_exec` with streaming output
- `__version__` now reads from package metadata instead of a hardcoded string
- Smoke test removed `release-check --dry-run` (requires `OPENAI_API_KEY`); replaced with `repo-summary .`

### Changed

- README and GitHub Pages updated to v0.4.1
- `docs/index.html` restructured: 6-card architecture grid, commands split by API-key requirement, links as 2-column grid
- `docs/COMMAND_SURFACE.md` updated with `docs-audit` and corrected smoke-test coverage table

---

## [v0.4.0] — 2026-05-23

### Added — mqlaunch integration

- `mq-agent-menu.sh` (macos-scripts) — 12-item agent menu: REPO ANALYSIS (1-4), AI COMMANDS (5-8), ENVIRONMENT (9-10), MCP LOCAL TOOLS (11-12)
- `mqlaunch agent ...` command surface for doctor, score, audit, release-check, MCP status and MCP tools
- 6 direct prompt commands wired into mqlaunch: `agent score`, `agent audit`, `agent doctor`, `agent release-check`, `agent mcp-status`, `agent mcp-tools`
- `scripts/smoke-mqlaunch.sh` — smoke test that verifies `mqlaunch agent ...` can reach mq-agent without a live session
- `docs/MQLAUNCH_INTEGRATION.md` — bridge architecture, available commands, and smoke-test usage

### Changed

- README: v0.4.0 status section; mqlaunch bridge section added; Roadmap updated
- ROADMAP: v0.4.0 marked done; v0.5.0 is autonomous loop mode

### Version

- Bumped to `0.4.0`

---

## [v0.3.0] — 2026-05-23

### Added — local tool orchestration

- `mq_agent/tools/mcp_registry.py` — `MCPToolSpec` dataclass, `classify_tool_name()`, and five safety classes: `read-only`, `write-capable`, `subprocess`, `dangerous`, `unknown`
- `mq-agent mcp status` — checks mq-mcp reachability and reports tool counts by safety class
- `mq-agent mcp tools` — lists all MCP-discovered tools with safety class and description
- `mq-agent tools --describe <name>` — shows description, schema, examples and safety class for a tool
- `mq-agent tools --mcp` — includes discovered MCP tools alongside built-in tools
- `mq-agent tools --json` — JSON output for built-in and/or MCP tool listing
- `mq-agent run-tool <tool>` — runs a specific MCP tool through mq-agent safety gates; `--arg key=value` for arguments
- `docs/MCP_INTEGRATION.md` — architecture and usage guide for mq-mcp integration
- `docs/TOOL_ROUTING.md` — safety classification reference and routing rules

### Changed

- `mq_agent/tools/mcp_bridge.py` — added `list_tool_specs()`, `describe_tool()`, `not_reachable_message()`, and `_fetch_tools_raw()` for structured metadata; backward-compatible
- `mq-agent tools` — now accepts `--describe`, `--mcp`, and `--json` flags
- README updated with v0.3.0 status, new CLI commands, and test count (70, was 37)
- ROADMAP updated: v0.3.0 marked complete, v0.4.0 is mqlaunch integration

### Safety

- Unknown MCP tools are blocked by default — no classification, no execution
- Write-capable and subprocess tools require `--approve` to run
- Dangerous tools require `--dangerous` to run
- Dry-run mode previews the intended MCP call without contacting mq-mcp
- Fail-closed: when mq-mcp is unavailable, `run-tool` exits with a clear error and startup instructions

### Tests

- `tests/test_mcp.py` — 33 new tests covering: name classification (17), `MCPToolSpec` construction and round-trip (9), bridge behavior when unavailable (6), safety count validation (1)
- Total: 70 tests pass (was 37) — no OpenAI API key or mq-mcp server required

### Version

- Bumped to `0.3.0`

---

## [v0.2.4] — 2026-05-23

### Added — docs sync + self-checking

- `scripts/check-docs-consistency.sh` — verifies version sync across VERSION, pyproject.toml, README badge, README status section, CHANGELOG, and docs/index.html; blocks stale score strings (`70/100`, `8/16`) and old version references
- `release-check.sh` — pre-release gate: tests, lint, docs consistency
- Docs consistency step added to `tests.yml` CI workflow
- ROADMAP rewritten to reflect actual done/next/later state (was showing everything as unchecked)

### Fixed — v0.2.4

- `docs/index.html` version badge corrected from `v0.2.1` to `v0.2.4`
- README status badge and section heading updated from `v0.2.3` to `v0.2.4`
- `scripts/check-install.sh`: `doctor` now uses `|| true` (matches CI, avoids failure without `OPENAI_API_KEY`)
- Version bumped to `0.2.4` in VERSION and pyproject.toml

---

## [v0.2.3] — 2026-05-23

### Added — credibility polish

- `Proof` section in README — lists what is actually verified
- `scripts/check-install.sh` — local install smoke test
- `.github/workflows/install-smoke.yml` — CI smoke test (no API key)
- README `Demo` section updated with real 100/100 output
- README status section updated to `v0.2.3`

### Changed — v0.2.3

- Version bumped to `0.2.3`

---

## [v0.2.2] — 2026-05-23

### Added — demo polish

- `docs/DEMO.md` — end-to-end walkthrough with real command output
- `docs/COMMANDS.md` — full command reference with safety modes and flags
- `docs/SAFETY_CONTRACT.md` — what the agent may/must not do, blocked patterns, audit trail
- `docs/MQ_ECOSYSTEM.md` — mqlaunch, mq-agent, mq-hal, mq-mcp, repo-signal integration map
- `SKILLS.md` + `skills/` — four skill definitions: repo-audit, release-readiness, signal-assessment, ci-diagnosis
- README: 30-second demo section, Use cases, tiered install (dev/GitHub/PyPI)
- GitHub: 11 topics set

### Fixed — v0.2.2

- `read_file()` accepts `file_path` kwarg (GPT-4o natural argument compat)
- `signal_tools.py` ruff + mypy clean (UP035, no-redef, import sort)
- `mcp_bridge` list_tools return type narrowed to `list[str]`
- planner/verifier: `json.loads(content or "{}")` — `str | None` guard
- TUI: `BINDINGS` type aligned with Textual `App` base class
- TUI: `Log()` markup kwarg removed (not supported)
- CI: `--system` flag removed from uv install; `[signal]` extra added
- `python-dotenv` auto-load from `~/mq-agent/.env` and `./.env`

### Changed — v0.2.2

- Version bumped to `0.2.2`

---

## [v0.2.0] — 2026-05-23

### Added — repo-signal integration

- `mq_agent/tools/signal_tools.py` — four tool wrappers around repo-signal's public API:
  - `repo_scan` — full repo scan: project type, languages, tooling, entry points, focus areas
  - `repo_readme_score` — README quality score 0–100 with visual bar and per-check breakdown
  - `repo_publish_checklist` — publish readiness checklist with grouped checks and action hints
  - `repo_analyze` — full repo-signal analysis report (markdown)
  - `repo_signal_json` — combined structured dict for use by agents and CI
- `mq_agent/agents/signal_agent.py` — `SignalAgent`: static signal pass + AI improvement plan
- `mq-agent signal [path]` — full assessment with overall score, README gaps, focus areas, AI plan
- `mq-agent score [path]` — instant README score + publish checklist (no AI, no API key needed)
- All four signal tools registered in `TOOL_REGISTRY` and `SAFE_TOOLS`
- `repo-signal` added as `[signal]` optional extra in `pyproject.toml`
- `mq-agent doctor` now shows repo-signal availability
- 11 new tests in `tests/test_signal_tools.py` (37 total)

### Changed — v0.2.0

- Version bumped to `0.2.0`

### Fixed — signal_tools syntax

- `*expr or fallback` syntax error inside list literals in signal_tools.py

---

## [v0.1.0] — 2026-05-23

### Added — core orchestration layer

- `Planner` — OpenAI gpt-4o backed structured plan generation from goals
- `Executor` — tool registry routing with dry-run and safety gate enforcement
- `Verifier` — per-step AI verification using gpt-4o-mini
- `Memory` — two-level memory: session (ephemeral) and persistent (JSON on disk)
- `SafetyGate` — four safety modes: `read-only`, `suggest`, `execute`, `dangerous`
- `AgentState` — structured state object tracking plan, context and progress
- Git tools: `git_status`, `git_log`, `git_diff`, `git_branch`, `git_remote`
- Shell tools: `run_command` with blocked dangerous pattern list
- Repo tools: `repo_summary`, `list_files`, `read_file`, `find_files`
- MCP bridge: HTTP bridge to mq-mcp server
- `AuditAgent`, `ReleaseAgent`, `CIAgent`, `DocsAgent`
- Typer CLI with `audit`, `plan`, `release-plan`, `release-check`, `repo-summary`, `run`, `fix-ci`, `doctor`, `tools`, `tui`
- All commands support `--dry-run` and `--json`
- Textual TUI with sidebar navigation and live log output
- GitHub Actions CI: tests + lint + type check on every push
- 26 unit tests, no OpenAI calls required
- Declarative task YAML: `release.yaml`, `audit.yaml`, `fix_ci.yaml`

### Fixed — v0.1.0

- `git_log` parameter renamed `n` → `limit` to match GPT-4o natural arg generation
- `git_branch`, `git_remote`, `find_files`, `which` added to `SAFE_TOOLS`
- Executor: read-only mode now continues past step failures instead of stopping

---

## [Unreleased]

### Planned for v0.2.0

- repo-signal integration
- repository audit scoring
- release readiness scoring
- semantic repository memory
