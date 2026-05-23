# Changelog

All notable changes to mq-agent are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

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
