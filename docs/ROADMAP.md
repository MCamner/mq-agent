# mq-agent Roadmap

mq-agent is a terminal-native AI agent orchestrator for the mq ecosystem.

It connects safe local execution, repo intelligence, MCP tools, mqlaunch workflows,
semantic repository memory and future agent loops into one controlled command
surface.

---

## Current status

Latest stable release:

```text
v0.8.0 — multi-agent workflows
```

Completed foundation:

* Terminal-native CLI
* Planner / Executor / Verifier architecture
* Safety modes
* Tool registry
* repo-signal integration
* mq-mcp bridge
* mqlaunch integration
* Command surface documentation
* Semantic repository memory
* GitHub Pages documentation
* Release hygiene and docs consistency checks
* Protected `main` workflow

---

## Release map

| Version | Theme                                        | Status  |
| ------- | -------------------------------------------- | ------- |
| v0.1.0  | Project foundation                           | Done    |
| v0.2.0  | Repo productization                          | Done    |
| v0.3.0  | Local tool orchestration via mq-mcp          | Done    |
| v0.4.0  | mqlaunch integration                         | Done    |
| v0.4.1  | Consistency, readability and release hygiene | Done    |
| v0.5.0  | Semantic repository memory                   | Done    |
| v0.5.1  | Semantic memory hardening                    | Done    |
| v0.5.2  | mcp start/stop process management            | Done    |
| v0.6.0  | Controlled agent loops (task runner)         | Done    |
| v0.6.1  | Orchestration stabilization checkpoint       | Done    |
| v0.7.0  | Browser-assisted workflows                   | Done    |
| v0.8.0  | Multi-agent workflows                        | Done    |
| v1.0.0  | Stable local agent platform                  | Next    |

---

## Completed

### v0.1.0 — Foundation

* [x] CLI foundation
* [x] Project structure
* [x] Core agent concepts
* [x] Basic docs
* [x] Local development setup

### v0.2.0 — Productization

* [x] README polish
* [x] GitHub Pages front door
* [x] Demo docs
* [x] Safety docs
* [x] Release checklist
* [x] repo-signal scoring
* [x] Publish checklist proof

### v0.3.0 — Local tool orchestration via mq-mcp

* [x] MCP bridge
* [x] MCP status command
* [x] MCP tool listing
* [x] MCP tool safety classes
* [x] Tool metadata inspection
* [x] `run-tool` command
* [x] Docs for MCP integration
* [x] Tests for local tool orchestration

### v0.4.0 — mqlaunch integration

* [x] `mqlaunch agent`
* [x] Direct mqlaunch agent commands
* [x] 12-item mqlaunch agent menu
* [x] 6 direct prompt commands
* [x] smoke test for mqlaunch bridge
* [x] mqlaunch integration docs
* [x] command surface docs
* [x] README proof updates

### v0.4.1 — Consistency, readability and release hygiene

* [x] Source readability pass
* [x] Docs consistency guard
* [x] Command count guard
* [x] `COMMAND_SURFACE.md` as single source of truth
* [x] Release hygiene cleanup
* [x] GitHub release
* [x] GitHub Pages deployment
* [x] Protected `main` workflow

### v0.5.0 — Semantic repository memory

* [x] `mq-agent memory status`
* [x] `mq-agent memory build`
* [x] `mq-agent memory refresh --approve`
* [x] repo-signal semantic upload bridge
* [x] vector store status detection
* [x] dry-run default for memory build
* [x] explicit approval for memory refresh
* [x] semantic memory docs
* [x] memory smoke test
* [x] tests for memory helpers
* [x] README semantic memory section
* [x] GitHub release
* [x] GitHub Pages deployment

---

### v0.5.1 — Semantic memory hardening

* [x] `mq-agent memory doctor` — diagnose environment with per-item status and actionable fixes
* [x] `mq-agent memory doctor --json` — machine-readable diagnostics
* [x] `mq-agent memory status --json` — machine-readable status output
* [x] Example output in `docs/SEMANTIC_MEMORY.md`
* [x] Memory proof section in README with verified output
* [x] `release-check.sh` includes memory smoke
* [x] Missing vector store reported clearly with fix instruction
* [x] Missing repo-signal reported clearly with fix instruction
* [x] Refresh never runs without `--approve`
* [x] 18 CLI-level tests — dry-run default, approval gate, JSON output, doctor diagnostics
* [x] Tests pass locally (94 total)
* [x] GitHub Actions pass
* [x] GitHub release `v0.5.1` exists

---

### v0.6.0 — Controlled agent loops (task runner)

* [x] `mq-agent task list` — list available YAML task workflow files
* [x] `mq-agent task list --json` — machine-readable task list
* [x] `mq-agent task run <name>` — execute declarative YAML workflow via tool registry
* [x] `mq-agent task run <name> --dry-run` — preview steps without execution
* [x] `mq-agent task run <name> --json` — machine-readable step results
* [x] `mq_agent/core/task_runner.py` — `load_task`, `run_task`, `find_task_files`
* [x] Task lookup by filename stem OR internal YAML `name:` field
* [x] `tests/test_task_runner.py` — 18 tests
* [x] Tool registry hardened — `_EXCLUDE_DIRS`, `write_file`, `repo_signal_json`, timeout 120s
* [x] Task YAML args corrected (`suffix→pattern`, `n→limit`, `ci.yml→tests.yml`)
* [x] 134 tests total

---

### v0.6.1 — Orchestration Stabilization

Goal:

Stabilize the existing orchestration runtime before adding more browser
automation or multi-agent behavior.

Rules:

* [x] Do not rewrite existing Planner / Executor / Verifier.
* [x] Do not rewrite TUI.
* [x] Do not change mqlaunch layout.
* [x] Do not duplicate task runner logic.
* [x] Do not start new multi-agent workflows.
* [x] Preserve all current commands.
* [x] Add architecture docs around current orchestration flow.
* [x] Identify coupling between CLI, TUI, tasks, tools, memory and MCP.
* [x] Add tests that lock current no-API command behavior.

Artifacts:

* [x] `docs/ARCHITECTURE.md` — current orchestration flow, boundaries and coupling risks
* [x] `tests/test_orchestration_contract.py` — command and registry contract tests

Dependency note:

v0.7.0 browser-assisted workflows and v0.8.0 multi-agent workflows are already
implemented. Future expansion in those areas should depend on this stabilization
checkpoint: preserve current commands, keep browser automation read-only unless
explicitly re-scoped, and avoid adding new swarm behavior without contract tests.

---

### v0.7.0 — Browser-assisted workflows

* [x] `mq-agent browser inspect <url>` — structured URL metadata: title, description, h1/h2, links, word count
* [x] `mq-agent browser summarize <url>` — plain-text content summary
* [x] `mq-agent browser verify-release <url>` — release page field verification; `--tag <v>` for version check
* [x] `mq_agent/tools/browser_tools.py` — `fetch_url`, `inspect_url`, `summarize_url`, `verify_release_url`
* [x] URL safety gate: blocks `file://`, `ftp://`, `data:`, `javascript:` schemes
* [x] Browser tools registered in `TOOL_REGISTRY` — usable in task YAML workflows
* [x] `tasks/browser_verify.yaml` — declarative browser verification task
* [x] `tests/test_browser.py` — 27 tests (URL safety, HTML parsing, CLI commands)
* [x] 161 tests total

### Non-goals (v0.7.0)

* No credential handling
* No hidden form submission
* No checkout/payment flows
* No unsafe automation

---

### v0.8.0 — Multi-agent workflows

* [x] `mq-agent swarm list` — list swarm configs with agents and safety classes
* [x] `mq-agent swarm plan <config>` — dry plan; no API, no execution
* [x] `mq-agent swarm run <config> [path]` — execute swarm, unified report
* [x] `mq-agent swarm audit [path]` — audit + signal + docs
* [x] `mq-agent swarm release-check [path]` — CI + audit + release
* [x] `AgentManifest` — declares purpose, safety_class, allowed_tools, requires_approve, output_contract, failure_behavior
* [x] `SwarmRunner` — dispatches agents, collects results, handles failures per manifest policy
* [x] `--approve` gate for write-capable agents
* [x] Dry-run requires no API key
* [x] Built-in swarm configs: `audit`, `release-check`, `ci`
* [x] `tests/test_swarm.py` — 29 tests
* [x] 190 tests total

---

## v1.0.0 — Stable local agent platform

Goal:

Make mq-agent stable enough to use as the default local agent surface for the mq
ecosystem.

### v1.0.0 requirements

* [ ] Stable CLI command surface
* [ ] Stable config format
* [ ] Stable safety model
* [ ] Stable memory model
* [ ] Stable mqlaunch integration
* [ ] Stable mq-mcp integration
* [ ] Stable repo-signal integration
* [ ] Complete docs
* [ ] Complete examples
* [ ] Complete release checklist
* [ ] Green CI
* [ ] Protected main branch
* [ ] Versioned GitHub release
* [ ] GitHub Pages documentation
* [ ] No known critical safety gaps

---

## Long-term ideas

These are intentionally not scheduled yet.

* Local model fallback
* Ollama integration
* HAL-style conversational shell
* Visual TUI dashboard
* Repository health history
* Agent-generated release notes
* Agent-generated docs diffs
* Cross-repo ecosystem memory
* Integration with macos-scripts
* Integration with mq-hal
* Integration with mq-ums
* Integration with mq-mcp tool safety map
* Semantic memory comparison between releases

---

## Design principles

mq-agent should remain:

* terminal-native
* explicit
* safe by default
* observable
* testable
* local-first
* repo-aware
* dry-run friendly
* approval gated
* useful without hiding execution

The model should assist the operator, not replace the operator.

---

## Safety principles

mq-agent must never:

* run destructive commands silently
* upload memory silently
* commit secrets
* bypass approval gates
* hide shell execution
* treat AI output as automatically trusted
* mutate repositories without explicit approval

Every powerful feature must have:

* dry-run mode
* JSON output when useful
* clear status output
* test coverage
* documentation
* failure behavior

---

## Current recommended next step

Work on:

```text
v0.7.0 — browser-assisted workflows
```

This adds controlled browser-adjacent workflows for research, documentation
and release verification.
