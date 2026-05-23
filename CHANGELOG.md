# Changelog

All notable changes to mq-agent are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

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
