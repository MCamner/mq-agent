# mq-agent Roadmap

mq-agent is a terminal-native workflow orchestration runtime for the mq ecosystem.

It connects safe local execution, repo intelligence, MCP tools, mqlaunch workflows,
and semantic repository memory into one controlled, operator-driven orchestration
surface.

---

## Current status

Latest stable release:

```text
v0.8.0 — controlled specialist orchestration
```

Current recommended next step:

```text
v0.9.0 — orchestration kernel consolidation
```

Completed foundation:

* Terminal-native CLI
* Planner / Executor / Verifier architecture
* Safety modes
* Tool registry
* repo-signal integration (v0.7.0+ with version guard)
* mq-mcp bridge
* mqlaunch integration
* Command surface documentation
* Semantic repository memory
* GitHub Pages documentation
* Release hygiene and docs consistency checks
* Protected `main` workflow
* Browser-assisted verification workflows (read-only, operator-approved)
* Declarative task runner with `{{step:name}}` templates
* Controlled specialist orchestration
* `run_task` tool — task chaining

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
| v0.6.1  | Orchestration stabilization                  | Done    |
| v0.7.0  | Browser-assisted verification workflows      | Done    |
| v0.8.0  | Controlled specialist orchestration          | Done    |
| v0.9.0  | Orchestration kernel consolidation           | Next    |
| v1.0.0  | Stable orchestration platform                | Planned |

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

### v0.6.1 — Orchestration stabilization

* [x] Tool registry hardened — excludes, `write_file`, `repo_signal_json`, timeout 120s
* [x] Task YAML args corrected (`suffix→pattern`, `n→limit`, `ci.yml→tests.yml`)
* [x] `{{step:name}}` template system — string args resolved from prior step output
* [x] `run_task` tool registered — tasks can chain other tasks
* [x] Version guard for repo-signal — clear error when too old
* [x] 204 tests total

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

### Architectural guardrails (v0.7.0)

* Browser workflows must be read-only by default
* No credential capture or storage
* No hidden form submission
* No purchase, booking or account actions
* No autonomous browser control
* All browser actions require explicit operator confirmation
* Browser results must be inspectable and citeable
* Browser workflow logic must use existing task/orchestration systems
* Do not create a second workflow engine

---

### v0.8.0 — Controlled specialist orchestration

This phase coordinates specialized agents through the existing task runner and
safety model. Each agent declares its purpose, safety class, allowed tools, and
failure behavior via `AgentManifest`.

The goal is planner-driven specialization, not autonomous multi-agent behavior.

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

## v0.9.0 — Orchestration kernel consolidation

Goal:

Stabilize orchestration boundaries and normalize runtime coordination before the
v1.0.0 stable release. No new features — only consolidation.

### v0.9.0 focus

* Normalize orchestration lifecycle — planner / executor / verifier contracts
* Unify task execution model — consistent step contracts across task runner and specialist orchestration
* Separate orchestration from presentation — CLI output must not bleed into core logic
* Formalize runtime provider layer — tool registry, MCP bridge, signal integration
* Reduce architectural drift — remove or document any divergent patterns
* Strengthen state consistency — no silent state across step boundaries
* Improve workflow composability — tasks and swarm configs are interchangeable primitives

### Non-goals (v0.9.0)

* No redesign of TUI or CLI surface
* No new autonomous systems
* No additional orchestration modes
* No uncontrolled browser automation
* No duplicate orchestration engines

---

## v1.0.0 — Stable orchestration platform

Goal:

Publish mq-agent as a stable, documented orchestration runtime for the mq
ecosystem. The platform is stable when its contracts are locked and its
orchestration boundaries are enforced.

### v1.0.0 requirements

* [x] Stable CLI command surface — `COMMAND_SURFACE.md` is single source of truth
* [ ] Stable config format
* [x] Stable safety model — read-only / suggest / execute / approve gates
* [x] Stable memory model — dry-run default, explicit `--approve`
* [x] Stable mqlaunch integration — bridge tested, menu + direct commands
* [x] Stable mq-mcp integration — start/stop, tool listing, safety classes
* [x] Stable repo-signal integration — version guard, suggest.v1, signal_json
* [x] Stable orchestration contracts — planner / executor / verifier / task runner (v0.9.0)
* [ ] Complete docs
* [ ] Complete examples
* [x] Complete release checklist — `release-check.sh` verified
* [x] Green CI
* [x] Protected main branch
* [x] Versioned GitHub releases — v0.6.0, v0.7.0, v0.8.0 published on GitHub
* [x] GitHub Pages documentation
* [x] No known critical safety gaps

---

## Long-term ideas

These are intentionally not scheduled yet.

* Local model fallback
* Ollama integration
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

## Research / Experimental

These ideas are architecturally interesting but conflict with the current
orchestration philosophy. They are not on the roadmap mainline. Any
implementation must be isolated, gated, and not merged into the core runtime.

* HAL-style conversational shell — autonomous conversational loops break the explicit approval model
* Autonomous looping agents — recursive agent execution without operator checkpoints
* Self-modifying task graphs — tasks that generate and run new tasks at runtime
* Uncontrolled browser automation — beyond operator-approved, read-only browser workflows

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
v0.9.0 — orchestration kernel consolidation
```

All foundation features are complete. The next step is consolidating orchestration
boundaries, normalizing contracts, and separating presentation from core logic
before the v1.0.0 stable release. No new features — only consolidation.
