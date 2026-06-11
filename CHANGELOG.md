# Changelog

All notable changes to mq-agent are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

## [v1.13.0] — 2026-06-11

### Added

* Stack truth export — `stack export` upgraded from a status table to a durable
  truth snapshot combining contract-check and release-check, written as a dated
  Markdown note to mqobsidian (`mq_agent/tools/stack_truth.py`, registered as
  the `stack_truth_export` tool).
* `mq-agent stack truth-export` — primary name for the stack truth export;
  `stack export` is kept as a backwards-compatible alias.
* `docs/STACK_TRUTH_EXPORT.md` — reference documentation.
* `mq-agent stack contract-check --ci` / `stack release-check --ci` — CI mode:
  sibling repos missing from the workspace are reported as SKIPPED instead of
  failing the gate; the CI checkout itself is detected via its directory name
  and fully validated.
* `_ci_repo_path()` helper in `stack_tools.py`.
* `mode` field (`ci` / `local`) in the JSON output of both gates.
* 21 new tests (`tests/test_stack_ci_mode.py`).

### Fixed

* `stack truth-export` / `stack export` now defaults to the dated note path
  (`~/mqobsidian/memory/stack-truth/YYYY-MM-DD-mq-stack-truth.md`) as documented;
  previously the CLI always passed the old `05_RELEASE_STATUS.md` path.

### Changed

* `.github/workflows/mq-stack-gate.yml` split into two jobs: `pr-gate` runs the
  fast `--ci` gates on pull requests (isolated from sibling-repo drift);
  `full-stack-gate` keeps the multi-repo checkout for pushes to `main`, a
  nightly cron run, and manual dispatch.
* `stack contract-check` status model extended with SKIPPED (CI mode only).

## [v1.12.0] — 2026-06-10

### Added

* `.github/workflows/mq-stack-gate.yml` — GitHub Actions workflow for MQ stack gates.
* CI checks out the active MQ stack repos into one workspace.
* CI links the checked-out repos into the `~/...` layout expected by `MQ_STACK_REPOS`.
* `mq-agent stack contract-check --json` now runs on pull requests and pushes to `main`.
* `mq-agent stack release-check --json` now runs on pull requests and pushes to `main`.
* `.mq/repo-contract.json` now declares `ci_stack_gate.v1` for mq-agent.

### Changed

* Version bumped to `1.12.0` in `VERSION`, `pyproject.toml`, README badge and repo contract.
* Roadmap marks v1.12.0 as complete and sets v1.13.0 as mqobsidian stack truth export.

## [v1.11.0] — 2026-06-10

### Added

* `mq-agent stack contract-check` — validates `.mq/repo-contract.json` manifests across MQ stack repos.
* `mq-agent stack contract-check --json` — machine-readable output.
* `_contract_entry()` helper in `stack_tools.py` — READY / REVIEW / DRIFT / BLOCKED per repo.
* `REQUIRED_CONTRACT_FIELDS` constant in `stack_tools.py`.
* `schemas/mq_stack_repo_contract.schema.json` — JSON Schema for repo contract manifests.
* `.mq/repo-contract.json` in all active MQ stack repos.
* `docs/STACK_CONTRACT_GATE.md` — reference documentation.

## [v1.10.0] — 2026-06-10

### Added

* `mq-agent stack release-notes` — draft release notes from git commits since last tag.
* `mq-agent stack release-notes --repo <name>` — single repo filter.
* `mq-agent stack release-notes --json` — machine-readable output.
* `docs/STACK_RELEASE_NOTES.md` — reference documentation.

## [v1.9.0] — 2026-06-10

### Added

* `mq-agent stack report` — consolidated per-repo score, trend, alert and readiness view.
* `mq-agent stack release-check` — local release gate across all stack repos.
* JSON output for stack report and release gate.
* `docs/STACK_REPORT.md` — reference documentation.

## [v1.8.0] — 2026-06-10

### Added

* `mq-agent stack alert` — threshold-based regression detection.
* `mq-agent stack sweep --alert` — inline alert at end of sweep.
* Configurable `--threshold`, `--min-score` and JSON output.
* `docs/STACK_ALERT.md` — reference documentation.

## [v1.7.0] — 2026-06-10

### Added

* Stack sweep history persisted to `~/.mq-agent/sweep-history.jsonl`.
* `mq-agent stack history` — trend table across past sweeps.
* `mq-agent stack history --diff` and `--json`.
* `docs/STACK_HISTORY.md` — reference documentation.

## [v1.6.0] — 2026-06-10

### Added

* `mq-agent stack sweep` — run repo-signal over every MQ stack repo.
* `--brain`, `--decide`, `--dry-run` and `--json` modes for stack sweep.
* mqlaunch agent menu item 18 — stack health sweep.
* `docs/STACK_HEALTH.md` — reference documentation.

## [v1.5.0] — 2026-06-10

### Added

* End-to-end MQ stack demo flow: signal → review → release-check.
* mqlaunch demo-flow command and menu integration.
* `docs/DEMO.md` rewritten as canonical walkthrough.

## [v1.4.0] — 2026-06-04

### Added

* mq-image-analyze MCP endpoint registration.
* Visual architecture context in review commands via `--architecture-image` / `--visual`.
* Read-only safety classification for visual perception tool families.

## [v1.3.0] — 2026-05-31

### Added

* Architecture-memory context surfaced after review findings.
* `--fast` review mode routing through mq-mcp Class A policy.
* Learn status/search/explain commands.
* Optional bridge helpers for architecture decisions and learned patterns.

## [v1.2.0] — 2026-05-31

### Added

* Semantic memory search/store commands.
* MCP status enrichment with semantic memory and orchestration contract checks.
* Docs and examples for semantic memory workflows.

## [v1.1.0] — 2026-05-31

### Added

* Review file/diff/repo orchestration through mq-mcp.
* Security, architecture and risk flags forwarded to mq-mcp review contracts.
* Dry-run support for review commands.
* Orchestration contract validation in `mq-agent doctor`.

## [v1.0.0] — 2026-05-26

### Added

* Stable orchestration platform release.
* Rich CLI rendering helpers and diagnostics module extracted from `main.py`.
* Configuration-driven model selection.
* Full architecture, examples and safety documentation.

## [v0.9.0] — 2026-05-26

### Added

* Orchestration contract suite for PlanStep, StepResult, AgentManifest, AgentState and tool registry.
* `MqAgentConfig` config model with environment override support.
* Runtime boundary documentation for Executor loop and SwarmRunner.

## [v0.8.0] — 2026-05-24

### Added

* Controlled swarm orchestration: list, plan, run, audit and release-check.
* Browser-safe URL inspection and release verification workflows.
* Declarative swarm audit task workflow.

## [v0.7.0] — 2026-05-24

### Added

* Browser inspection, summarization and release verification commands.
* Browser tool registry integration and URL safety gates.

## [v0.6.0] — 2026-05-24

### Added

* Declarative YAML task runner.
* `mq-agent task list` and `mq-agent task run` with dry-run and JSON output.

## [v0.5.2] — 2026-05-24

### Added

* `mq-agent mcp start`, `mq-agent mcp stop` and background process management.
* PID-file based mq-mcp lifecycle helpers.

## [v0.5.1] — 2026-05-24

### Added

* Memory doctor diagnostics and JSON output.
* Semantic memory status hardening and docs updates.

## [v0.5.0] — 2026-05-24

### Added

* Semantic repository memory via repo-signal.
* Memory build/refresh commands with explicit approval gates.

## [v0.4.1] — 2026-05-23

### Added

* Command surface documentation and docs consistency checks.
* `mq-agent docs-audit` command.
* Model override environment variables.

## [v0.4.0] — 2026-05-23

### Added

* mqlaunch integration and direct prompt command surface.
* `scripts/smoke-mqlaunch.sh` and bridge documentation.

## [v0.3.0] — 2026-05-23

### Added

* Local MCP tool orchestration layer.
* MCP status, MCP tools, tool description and run-tool commands.
* Tool safety classification model.

## [v0.2.4] — 2026-05-23

### Added

* Release hygiene and docs consistency checks.
* Release-check gate and documentation hardening.

## [v0.2.3] — 2026-05-23

### Added

* Proof section and install smoke test.
* GitHub Actions install smoke workflow.

## [v0.2.2] — 2026-05-23

### Added

* Demo polish, command docs, safety contract and MQ ecosystem docs.
* Skills directory and release-readiness examples.

## [v0.2.0] — 2026-05-23

### Added

* repo-signal integration.
* README scoring, publish checklist and signal commands.

## [v0.1.0] — 2026-05-23

### Added

* Core orchestration layer: Planner, Executor, Verifier, Memory and SafetyGate.
* Git, shell, repo and MCP bridge tools.
* Initial Typer CLI, Textual TUI and GitHub Actions CI.
