# Changelog

All notable changes to mq-agent are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [v0.1.0] — 2026-05-23

### Added

**Core orchestration layer**
- `Planner` — OpenAI gpt-4o backed structured plan generation from goals
- `Executor` — tool registry routing with dry-run and safety gate enforcement
- `Verifier` — per-step AI verification using gpt-4o-mini
- `Memory` — two-level memory: session (ephemeral) and persistent (JSON on disk)
- `SafetyGate` — four safety modes: `read-only`, `suggest`, `execute`, `dangerous`
- `AgentState` — structured state object tracking plan, context and progress

**Tools**
- `git_status`, `git_log`, `git_diff`, `git_branch`, `git_remote`
- `run_command` with blocked dangerous pattern list
- `repo_summary`, `list_files`, `read_file`, `find_files`
- `mcp_bridge` — HTTP bridge to mq-mcp server

**Agents**
- `AuditAgent` — read-only repository audit with planner + verifier loop
- `ReleaseAgent` — release validation and release plan generation
- `CIAgent` — CI failure diagnosis with test/lint/type context
- `DocsAgent` — documentation completeness audit

**CLI (Typer)**
- `mq-agent audit [path]`
- `mq-agent plan <goal>`
- `mq-agent release-plan`
- `mq-agent release-check [--approve]`
- `mq-agent repo-summary [path]`
- `mq-agent run <command> [--approve]`
- `mq-agent fix-ci`
- `mq-agent doctor`
- `mq-agent tools`
- `mq-agent tui`
- All commands support `--dry-run` and `--json`

**TUI**
- Textual dashboard with sidebar navigation and live log output
- Keyboard bindings: `enter` to run, `c` to clear, `q` to quit

**Infrastructure**
- `pyproject.toml` with hatchling build backend
- `uv` for package management
- `ruff` linting, `mypy` type checking
- GitHub Actions CI: tests + lint + type check on every push
- 26 unit tests, no OpenAI calls required
- `scripts/install.sh`
- Declarative task YAML: `release.yaml`, `audit.yaml`, `fix_ci.yaml`
- Prompt files: `prompts/planner.md`, `prompts/verifier.md`

### Fixed

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
